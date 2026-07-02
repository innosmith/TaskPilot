"""Angepinnter Konversations-Kontext: Dokumente leben in der ganzen Konversation.

Angehängte Dokumente (lokale Uploads, OneDrive) werden beim ersten Senden
einmalig via ``context_resolver`` extrahiert und als ``ConversationContextItem``
persistiert. Bei jedem weiteren Turn wird der angepinnte Korpus bis zu einem
Budget re-injiziert — wie bei Claude Desktop/ChatGPT bleibt ein Dokument damit
für Rückfragen sichtbar, statt nur im Request zu existieren, mit dem es
hochgeladen wurde.

Zusätzlich: tokenbudgetierter Konversationsverlauf als Message-Array für die
Hermes-Runtime (``run_conversation(conversation_history=...)``).
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConversationContextItem

logger = logging.getLogger(__name__)

# Budget für den re-injizierten Dokument-Korpus pro Turn. Deckt sich mit dem
# Resolver-Limit (context_resolver.MAX_TOTAL_CHARS) — bei 131k Tokens lokalem
# Kontextfenster entspricht das grob einem Viertel des Fensters.
PINNED_CONTEXT_BUDGET_CHARS = 100_000

# Verlaufs-Budget für die Hermes-Runtime: grosszügig, weil das lokale Modell
# 131k Tokens Kontext hat und die Hermes-Session-Kompression ab 70 % greift.
# ~200k Zeichen entsprechen grob 50–60k Tokens (deutscher Text).
HISTORY_BUDGET_CHARS = 200_000
HISTORY_MAX_MESSAGES = 200


async def persist_context_sources(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    context_sources: list | None,
) -> list[ConversationContextItem]:
    """Löst neue Kontext-Quellen auf und pinnt sie an die Konversation.

    Bereits gepinnte Quellen (gleicher ``source_ref``) werden nicht doppelt
    aufgelöst. Fehler blockieren den Chat nie — im Zweifel wird die Quelle
    einfach übersprungen (best-effort, wie beim bisherigen Resolver).
    """
    if not context_sources:
        return []

    existing_refs = {
        row.source_ref
        for row in (
            await db.execute(
                select(ConversationContextItem).where(
                    ConversationContextItem.conversation_id == conversation_id
                )
            )
        ).scalars()
        if row.source_ref
    }

    new_sources = []
    for src in context_sources:
        ref = str(src.get("upload_id") or src.get("item_id") or "")
        if ref and ref in existing_refs:
            continue
        new_sources.append(src)

    if not new_sources:
        return []

    try:
        from app.services.context_resolver import resolve_context_sources

        needs_graph = any(
            str(s.get("type", "")).startswith("onedrive") for s in new_sources
        )
        graph_client = None
        if needs_graph:
            from app.services.graph import get_graph_client

            graph_client = get_graph_client()

        ctx = await resolve_context_sources(new_sources, graph_client)
    except Exception:  # noqa: BLE001 - best-effort, darf den Chat nie blockieren
        logger.exception("Kontext-Quellen konnten nicht aufgelöst werden")
        return []

    # Auflösung den Quellen zuordnen: der Resolver liefert Dateien in der
    # Reihenfolge der Quellen (Ordner können mehrere Dateien liefern, dann
    # fehlt die 1:1-Zuordnung — source_ref bleibt in dem Fall leer).
    items: list[ConversationContextItem] = []
    resolved_by_name = {f["name"]: f for f in ctx.files}
    for src in new_sources:
        name = str(src.get("name") or "Dokument")
        f = resolved_by_name.pop(name, None)
        item = ConversationContextItem(
            conversation_id=conversation_id,
            source_type=str(src.get("type") or "local_upload"),
            source_ref=str(src.get("upload_id") or src.get("item_id") or "") or None,
            name=name,
            content=(f or {}).get("content", ""),
            char_count=len((f or {}).get("content", "")),
        )
        if item.content:
            db.add(item)
            items.append(item)
    # Übrige aufgelöste Dateien (z. B. aus Ordner-Quellen) ebenfalls pinnen.
    for f in resolved_by_name.values():
        item = ConversationContextItem(
            conversation_id=conversation_id,
            source_type="onedrive_file",
            source_ref=None,
            name=f["name"],
            content=f["content"],
            char_count=len(f["content"]),
        )
        db.add(item)
        items.append(item)

    await db.flush()
    return items


async def load_pinned_items(
    db: AsyncSession, conversation_id: uuid.UUID
) -> list[ConversationContextItem]:
    """Lädt alle angepinnten Kontext-Dokumente einer Konversation (chronologisch)."""
    result = await db.execute(
        select(ConversationContextItem)
        .where(
            ConversationContextItem.conversation_id == conversation_id,
            ConversationContextItem.pinned.is_(True),
        )
        .order_by(ConversationContextItem.created_at)
    )
    return list(result.scalars().all())


def build_pinned_context_block(
    items: list[ConversationContextItem],
    budget_chars: int = PINNED_CONTEXT_BUDGET_CHARS,
) -> str:
    """Baut den ``<attached_files>``-Block aus angepinnten Dokumenten.

    Neueste Dokumente haben Vorrang: Überschreitet der Korpus das Budget,
    werden die ältesten Dokumente zuerst gekürzt bzw. weggelassen (mit
    sichtbarem Hinweis statt stillem Wegschneiden).
    """
    if not items:
        return ""

    remaining = budget_chars
    kept: list[tuple[str, str]] = []  # (name, content) — neueste zuerst
    omitted: list[str] = []
    for item in reversed(items):
        if remaining <= 0:
            omitted.append(item.name)
            continue
        content = item.content or ""
        if len(content) > remaining:
            content = content[:remaining] + "\n\n[... Text gekürzt (Kontext-Budget) ...]"
        remaining -= len(content)
        kept.append((item.name, content))
    kept.reverse()

    parts = ["<attached_files>"]
    for name, content in kept:
        parts.append(f"\n## Datei: {name} (angepinnt)\n")
        parts.append(content)
    parts.append("\n</attached_files>")
    if omitted:
        parts.append(
            "\n[Hinweis: Folgende ältere Dokumente überschreiten das Kontext-Budget "
            f"und wurden weggelassen: {', '.join(reversed(omitted))}]"
        )
    return "\n".join(parts)


def build_conversation_history(
    messages: list,
    max_messages: int = HISTORY_MAX_MESSAGES,
    budget_chars: int = HISTORY_BUDGET_CHARS,
) -> list[dict]:
    """Konversationsverlauf als Message-Array (für ``conversation_history``).

    Neueste Nachrichten haben Vorrang; bei Budget-Überschreitung fallen die
    ältesten weg. Einzelne überlange Nachrichten werden nicht abgeschnitten,
    solange das Budget reicht — die Hermes-Kompression fängt lange Sessions ab.
    """
    history = [
        m for m in messages
        if getattr(m, "role", "") in ("user", "assistant") and (m.content or "").strip()
    ][-max_messages:]

    kept: list = []
    remaining = budget_chars
    for msg in reversed(history):
        cost = len(msg.content or "")
        if kept and remaining - cost < 0:
            break
        remaining -= cost
        kept.append(msg)
    kept.reverse()

    return [{"role": m.role, "content": m.content} for m in kept]

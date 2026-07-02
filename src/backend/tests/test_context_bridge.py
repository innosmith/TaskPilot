"""Tests für die Dokumenten-Kontext-Brücke (angepinnter Konversations-Kontext).

Prüft, dass angehängte Dokumente (lokale Uploads + OneDrive) über den
`conversation_context`-Service an die Konversation gepinnt und bei jedem Turn
als `<attached_files>`-Block re-injiziert werden. LLM/Graph/DB werden nicht
real aufgerufen.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.context_resolver import ResolvedContext


# ---------------------------------------------------------------------------
# Fake-DB-Helfer (kein echtes SQLAlchemy nötig)
# ---------------------------------------------------------------------------

class _FakeScalars(list):
    def all(self):
        return list(self)


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)


def _fake_db(existing_items=None):
    return SimpleNamespace(
        execute=AsyncMock(return_value=_FakeResult(existing_items or [])),
        add=Mock(),
        flush=AsyncMock(),
    )


def _item(name: str, content: str, pinned: bool = True, source_ref: str | None = None):
    return SimpleNamespace(
        name=name,
        content=content,
        char_count=len(content),
        pinned=pinned,
        source_ref=source_ref,
    )


# ---------------------------------------------------------------------------
# persist_context_sources — Pinnen neuer Quellen
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_local_only_skips_graph():
    """Ohne OneDrive-Quelle wird kein Graph-Client erstellt."""
    import uuid as _uuid

    from app.services import conversation_context as cc

    async def fake_resolve(sources, graph_client=None):
        assert graph_client is None
        ctx = ResolvedContext()
        ctx.add_file("a.txt", "INHALT", "Upload")
        return ctx

    db = _fake_db()
    with patch(
        "app.services.context_resolver.resolve_context_sources", fake_resolve
    ):
        items = await cc.persist_context_sources(
            db, _uuid.uuid4(),
            [{"type": "local_upload", "upload_id": "chat/x.txt", "name": "a.txt"}],
        )

    assert len(items) == 1
    assert items[0].content == "INHALT"
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_persist_onedrive_uses_graph():
    """OneDrive-Quelle lädt den Graph-Client."""
    import uuid as _uuid

    from app.services import conversation_context as cc

    captured = {}

    async def fake_resolve(sources, graph_client=None):
        captured["graph_client"] = graph_client
        ctx = ResolvedContext()
        ctx.add_file("cloud.docx", "CLOUD", "OneDrive")
        return ctx

    db = _fake_db()
    with patch(
        "app.services.context_resolver.resolve_context_sources", fake_resolve
    ), patch("app.services.graph.get_graph_client", return_value="GRAPH"):
        items = await cc.persist_context_sources(
            db, _uuid.uuid4(),
            [{"type": "onedrive_file", "item_id": "ABC", "name": "cloud.docx"}],
        )

    assert captured["graph_client"] == "GRAPH"
    assert items[0].content == "CLOUD"


@pytest.mark.asyncio
async def test_persist_deduplicates_existing_refs():
    """Bereits gepinnte Quellen (gleicher source_ref) werden nicht neu aufgelöst."""
    import uuid as _uuid

    from app.services import conversation_context as cc

    db = _fake_db(existing_items=[_item("a.txt", "ALT", source_ref="chat/x.txt")])
    resolve_mock = AsyncMock()
    with patch(
        "app.services.context_resolver.resolve_context_sources", resolve_mock
    ):
        items = await cc.persist_context_sources(
            db, _uuid.uuid4(),
            [{"type": "local_upload", "upload_id": "chat/x.txt", "name": "a.txt"}],
        )

    assert items == []
    resolve_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_empty_and_none():
    import uuid as _uuid

    from app.services import conversation_context as cc

    db = _fake_db()
    assert await cc.persist_context_sources(db, _uuid.uuid4(), []) == []
    assert await cc.persist_context_sources(db, _uuid.uuid4(), None) == []


@pytest.mark.asyncio
async def test_persist_never_raises():
    """Fehler bei der Auflösung blockieren den Chat nicht (leere Liste)."""
    import uuid as _uuid

    from app.services import conversation_context as cc

    async def boom(sources, graph_client=None):
        raise RuntimeError("kaputt")

    db = _fake_db()
    with patch("app.services.context_resolver.resolve_context_sources", boom):
        items = await cc.persist_context_sources(
            db, _uuid.uuid4(),
            [{"type": "local_upload", "upload_id": "chat/x.txt", "name": "x"}],
        )

    assert items == []


# ---------------------------------------------------------------------------
# build_pinned_context_block — Re-Injektion mit Budget
# ---------------------------------------------------------------------------

def test_pinned_block_empty():
    from app.services.conversation_context import build_pinned_context_block

    assert build_pinned_context_block([]) == ""


def test_pinned_block_contains_all_documents():
    from app.services.conversation_context import build_pinned_context_block

    block = build_pinned_context_block([
        _item("plan.md", "PLAN-INHALT"),
        _item("mail.txt", "MAIL-INHALT"),
    ])

    assert "<attached_files>" in block
    assert "plan.md" in block and "PLAN-INHALT" in block
    assert "mail.txt" in block and "MAIL-INHALT" in block


def test_pinned_block_budget_prefers_newest_and_notes_omissions():
    """Bei Budget-Überschreitung fallen die ältesten Dokumente sichtbar weg."""
    from app.services.conversation_context import build_pinned_context_block

    old = _item("alt.txt", "A" * 500)
    new = _item("neu.txt", "N" * 500)
    block = build_pinned_context_block([old, new], budget_chars=500)

    assert "N" * 500 in block
    assert "A" * 500 not in block
    assert "alt.txt" in block  # als weggelassen erwähnt
    assert "weggelassen" in block


def test_pinned_block_truncates_within_budget():
    from app.services.conversation_context import build_pinned_context_block

    block = build_pinned_context_block([_item("gross.txt", "X" * 1000)], budget_chars=200)

    assert "X" * 200 in block
    assert "X" * 201 not in block
    assert "gekürzt" in block


# ---------------------------------------------------------------------------
# build_conversation_history — tokenbudgetiertes Message-Array
# ---------------------------------------------------------------------------

def _msg(role: str, content: str):
    return SimpleNamespace(role=role, content=content)


def test_history_keeps_roles_and_order():
    from app.services.conversation_context import build_conversation_history

    history = build_conversation_history([
        _msg("user", "Frage 1"),
        _msg("assistant", "Antwort 1"),
        _msg("system", "ignorieren"),
        _msg("user", ""),
        _msg("user", "Frage 2"),
    ])

    assert history == [
        {"role": "user", "content": "Frage 1"},
        {"role": "assistant", "content": "Antwort 1"},
        {"role": "user", "content": "Frage 2"},
    ]


def test_history_budget_drops_oldest_whole_messages():
    """Budget schneidet ganze alte Nachrichten ab statt sie zu verstümmeln."""
    from app.services.conversation_context import build_conversation_history

    msgs = [_msg("user", f"Nachricht {i} " + "x" * 100) for i in range(10)]
    history = build_conversation_history(msgs, budget_chars=350)

    # Nur die neuesten Nachrichten passen, jede vollständig (keine Kürzung).
    assert all(m["content"].endswith("x" * 100) for m in history)
    assert history[-1]["content"].startswith("Nachricht 9 ")
    assert 0 < len(history) < 10
    assert history[0]["content"].startswith("Nachricht 7 ")


def test_history_never_empty_if_messages_exist():
    """Eine überlange letzte Nachricht wird trotzdem mitgenommen."""
    from app.services.conversation_context import build_conversation_history

    history = build_conversation_history([_msg("user", "y" * 5000)], budget_chars=100)
    assert len(history) == 1


# ---------------------------------------------------------------------------
# Agent-Prompt: Verlauf/Dokumente laufen NICHT mehr als Textblock im Prompt
# ---------------------------------------------------------------------------

def _patch_prompt_helpers():
    """Mockt die DB-gestützten Prompt-Bausteine (Regeln/Recall/Task-Briefing)."""
    import app.services.hermes_worker as hw
    from app.routers import chat

    return (
        patch.object(hw, "_build_rules_block", AsyncMock(return_value="")),
        patch.object(hw, "_build_recall_block", AsyncMock(return_value="")),
        patch.object(chat, "_build_task_briefing", AsyncMock(return_value="")),
    )


@pytest.mark.asyncio
async def test_build_agent_prompt_mentions_pinned_documents_rule():
    """Der Agent-Prompt erklärt, dass angepinnte Dokumente im Verlauf stehen."""
    from app.routers import chat

    p1, p2, p3 = _patch_prompt_helpers()
    with p1, p2, p3, patch.object(chat, "_load_agent_skills", return_value="(keine)"):
        prompt = await chat._build_agent_prompt("Was steht im Dokument?")

    assert "Angepinnte Dokumente" in prompt
    assert "Was steht im Dokument?" in prompt


# ---------------------------------------------------------------------------
# Code-Modus: angepinnte Dokumente als Kontext-Message (ohne Rückschritt)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_code_mode_pinned_context_message():
    import uuid as _uuid

    from app.routers import code_execute

    with (
        patch(
            "app.services.conversation_context.load_pinned_items",
            AsyncMock(return_value=[_item("daten.csv", "SPALTEN: a,b,c")]),
        ),
    ):
        msg = await code_execute._load_pinned_context_message(None, _uuid.uuid4())

    assert msg is not None
    assert msg["role"] == "user"
    assert "daten.csv" in msg["content"]
    assert "SPALTEN: a,b,c" in msg["content"]


@pytest.mark.asyncio
async def test_code_mode_pinned_context_empty_returns_none():
    import uuid as _uuid

    from app.routers import code_execute

    with patch(
        "app.services.conversation_context.load_pinned_items",
        AsyncMock(return_value=[]),
    ):
        msg = await code_execute._load_pinned_context_message(None, _uuid.uuid4())

    assert msg is None


@pytest.mark.asyncio
async def test_code_mode_pinned_context_never_raises():
    """Kontext-Fehler dürfen den Code-Flow nie blockieren (kein Rückschritt)."""
    import uuid as _uuid

    from app.routers import code_execute

    with patch(
        "app.services.conversation_context.load_pinned_items",
        AsyncMock(side_effect=RuntimeError("kaputt")),
    ):
        msg = await code_execute._load_pinned_context_message(None, _uuid.uuid4())

    assert msg is None


# ---------------------------------------------------------------------------
# Worker-Brücke (app.services.hermes_worker) — unverändert
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_attachment_context_maps_sources():
    """Task-Anhänge werden korrekt zu context_sources gemappt und injiziert."""
    from app.services import hermes_worker

    task = SimpleNamespace(attachments=[
        SimpleNamespace(
            filepath="/uploads/tasks/abc/file.pdf",
            filename="file.pdf",
            mime_type="application/pdf",
        ),
        SimpleNamespace(
            filepath="onedrive://ITEM123",
            filename="cloud.docx",
            mime_type=None,
        ),
    ])

    captured = {}

    async def fake_resolve(sources, graph_client=None):
        captured["sources"] = sources
        captured["graph_client"] = graph_client
        ctx = ResolvedContext()
        ctx.add_file("file.pdf", "PDF INHALT", "Upload")
        return ctx

    with patch(
        "app.services.context_resolver.resolve_context_sources", fake_resolve
    ), patch("app.services.graph.get_graph_client", return_value="GRAPH"):
        result = await hermes_worker._resolve_task_attachment_context(task)

    assert "<attached_files>" in result
    assert "PDF INHALT" in result

    local = next(s for s in captured["sources"] if s["type"] == "local_upload")
    assert local["upload_id"] == "tasks/abc/file.pdf"

    onedrive = next(s for s in captured["sources"] if s["type"] == "onedrive_file")
    assert onedrive["item_id"] == "ITEM123"

    # OneDrive-Quelle vorhanden → Graph-Client wurde geladen
    assert captured["graph_client"] == "GRAPH"


@pytest.mark.asyncio
async def test_task_attachment_context_no_attachments():
    from app.services import hermes_worker

    task = SimpleNamespace(attachments=[])
    assert await hermes_worker._resolve_task_attachment_context(task) == ""


@pytest.mark.asyncio
async def test_task_attachment_context_local_only_no_graph():
    """Nur lokale Anhänge → kein Graph-Client."""
    from app.services import hermes_worker

    task = SimpleNamespace(attachments=[
        SimpleNamespace(
            filepath="/uploads/tasks/abc/notes.txt",
            filename="notes.txt",
            mime_type="text/plain",
        ),
    ])

    captured = {}

    async def fake_resolve(sources, graph_client=None):
        captured["graph_client"] = graph_client
        ctx = ResolvedContext()
        ctx.add_file("notes.txt", "NOTIZEN", "Upload")
        return ctx

    with patch(
        "app.services.context_resolver.resolve_context_sources", fake_resolve
    ):
        result = await hermes_worker._resolve_task_attachment_context(task)

    assert captured["graph_client"] is None
    assert "NOTIZEN" in result

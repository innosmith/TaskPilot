"""Hermes Agent-Runtime Worker: verarbeitet queued AgentJobs via Hermes AIAgent.

Ersetzt den fruheren Nanobot-Worker. Laeuft als Hintergrund-Task im FastAPI-
Backend und pollt alle 10s die ``agent_jobs``-Queue. Hermes ist synchron
(``AIAgent.run_conversation`` blockiert), deshalb wird jeder Job ueber
``asyncio.to_thread`` ausgefuehrt, damit der Event-Loop frei bleibt.

Architektur (Spike-validiert, siehe docs/hermes-vs-nanobot-entscheidung.md):
- Persistenter ``AIAgent`` pro Worker (Provider ``custom`` -> Ollama ``/v1``).
- MCP-Tools werden einmalig via ``discover_mcp_tools()`` registriert (eigener
  Hintergrund-Event-Loop in Hermes) und vom Agent automatisch genutzt.
- Nach der LLM-Klassifikation laeuft dieselbe deterministische Post-Processing-
  Logik wie zuvor (JSON parsen, Task erstellen, Draft zuordnen).

Transparenz: ``reasoning_callback`` (echtes Thinking) und die Tool-Callbacks
werden in einen Job-Trace geschrieben (``metadata_json['trace']``), damit man
in der Agent-Queue nachvollziehen kann, was der Agent gedacht und getan hat.

Thinking-Politik: Standardmaessig AN (Transparenz + Demo). Der Disable-Hebel
fuer qwen3.5/3.6 ist ``extra_body.chat_template_kwargs.enable_thinking=False``
(``/no_think`` funktioniert in dieser Modellgeneration NICHT). Er ist als
opt-in-Policy vorbereitet (``_thinking_disabled``), aber bewusst nicht im
Default-Pfad scharfgeschaltet, da das Verhalten ueber Ollama ``/v1``
versionsabhaengig ist und vor Aktivierung live verifiziert werden muss.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update

from app.config import get_settings
from app.database import async_session
from app.models import AgentJob, BoardColumn, EmailTriage, Project, Task, User
from app.services.hermes_config import (
    get_hermes_home,
    populate_hermes_env,
    write_hermes_config,
)
from app.services.learning import record_episode
from app.services.notification import notify_agent_awaiting_approval, notify_task_suggested

logger = logging.getLogger("taskpilot.hermes_worker")

POLL_INTERVAL = 10
REAP_INTERVAL = 60
DRAFT_CLEANUP_INTERVAL = 300  # 5 Minuten
STALE_TIMEOUT_MINUTES = 30

HERMES_HOME = get_hermes_home()
# Hermes-native Skills (Progressive Disclosure via skill_view). Der Worker laedt sie
# nicht mehr als String, sondern weist den Agenten an, sie selbst zu laden.
EMAIL_TRIAGE_SKILL = HERMES_HOME / "skills" / "email-triage" / "SKILL.md"
EMAIL_TRIAGE_REFERENCES = HERMES_HOME / "skills" / "email-triage" / "references"
EMAIL_STYLE_SKILL = HERMES_HOME / "skills" / "email-style" / "SKILL.md"
# Legacy-Fallbacks (Flat-Dateien aus der Nanobot-Aera) -- nur falls die nativen
# Skills (noch) nicht ausgerollt sind. Werden nach erfolgreicher Migration entfernt.
LEGACY_TRIAGE_SKILL = HERMES_HOME / "skills" / "mail-triage.md"
LEGACY_STYLE_PROFILE = HERMES_HOME / "schreibstil-anthony.md"
# Rueckwaerts-Kompatibilitaet: einzelne Module/Tests referenzieren diese Namen noch.
TRIAGE_SKILL = EMAIL_TRIAGE_SKILL
STYLE_PROFILE = EMAIL_STYLE_SKILL

# Mapping alter (Nanobot-)Skill-Namen auf die neuen Hermes-Skill-Verzeichnisse.
# Generische AgentJobs koennen noch die alten Namen in ``metadata.skill`` tragen.
_SKILL_NAME_ALIASES: dict[str, str] = {
    "mail-triage": "email-triage",
    "crm-assistant": "crm-pipedrive",
    "signa-recherche": "signa-research",
}

PIPELINE_COLUMNS = {
    "focus": "a0000000-0000-0000-0000-000000000001",
    "this_week": "a0000000-0000-0000-0000-000000000002",
    "next_week": "a0000000-0000-0000-0000-000000000003",
    "this_month": "a0000000-0000-0000-0000-000000000005",
}

WORKER_SYSTEM_PROMPT = (
    "Du bist der TaskPilot-Agent von Anthony Smith (InnoSmith GmbH, Schweiz). "
    "Du nutzt deine MCP-Tools aktiv und behauptest nie, keinen Zugriff zu haben. "
    "Befolge die Instruktionen in der Nachricht exakt und Schritt fuer Schritt. "
    "Wenn du eine dauerhaft gueltige Tatsache ueber Anthony, einen Absender oder "
    "eine Arbeitsweise lernst (z. B. eine stabile Praeferenz oder Triage-Regel), "
    "halte sie knapp mit dem memory-Tool fest, damit sie kuenftig verfuegbar ist. "
    "Sprache: Schweizer Hochdeutsch (ss statt scharfem S, korrekte Umlaute ae/oe/ue als ä/ö/ü). "
    "Zeitzone: Europe/Zurich."
)

# ── Runtime-State ────────────────────────────────────────
_worker_task: asyncio.Task | None = None
_agent = None  # persistenter Worker-AIAgent
_runtime_ready = False
_runtime_lock: asyncio.Lock | None = None
_trajectory_shim_installed = False

# Trace-Sink fuer den aktuellen Job (Worker verarbeitet sequentiell).
_job_trace: list[dict] = []
_MAX_TRACE_EVENTS = 200


def _get_runtime_lock() -> asyncio.Lock:
    global _runtime_lock
    if _runtime_lock is None:
        _runtime_lock = asyncio.Lock()
    return _runtime_lock


def _install_trajectory_path_shim() -> None:
    """Buendelt Hermes-Trajektorien in ``~/.hermes/trajectories/`` statt im Backend-CWD.

    Hermes' ``save_trajectory`` schreibt relativ ins aktuelle Arbeitsverzeichnis
    (``trajectory_samples.jsonl`` / ``failed_trajectories.jsonl``) und bietet keinen
    Pfad-/Env-Hook. Damit die gesammelten Trajektorien (Grundlage fuer Inspektion +
    spaeteres Fine-Tuning) an einem definierten Ort liegen, ersetzen wir
    ``run_agent._save_trajectory_to_file`` durch einen Wrapper mit absolutem Pfad.
    Idempotent, best-effort -- darf den Worker-Start nie verhindern.
    """
    global _trajectory_shim_installed
    if _trajectory_shim_installed:
        return
    try:
        import run_agent
        from agent.trajectory import save_trajectory as _orig_save_trajectory

        traj_dir = HERMES_HOME / "trajectories"
        traj_dir.mkdir(parents=True, exist_ok=True)

        def _save_to_hermes_home(trajectory, model, completed, filename=None):
            if filename is None:
                base = "trajectory_samples.jsonl" if completed else "failed_trajectories.jsonl"
                filename = str(traj_dir / base)
            return _orig_save_trajectory(trajectory, model, completed, filename=filename)

        run_agent._save_trajectory_to_file = _save_to_hermes_home
        _trajectory_shim_installed = True
        logger.info("Trajektorien-Pfad-Shim aktiv -> %s", traj_dir)
    except Exception:  # noqa: BLE001 - best-effort
        logger.warning("Trajektorien-Pfad-Shim konnte nicht installiert werden (ignoriert)")


# ── Thinking-Policy ──────────────────────────────────────

# Jobtypen/Skills, bei denen Thinking deaktiviert werden DARF (rein mechanisch).
# Leer im Default: Thinking bleibt ueberall an (Transparenz). Erst nach
# Live-Verifikation gegen die Ollama-Version befuellen.
_THINKING_DISABLED_JOB_TYPES: set[str] = set()


def _thinking_disabled(job_type: str | None, skill: str | None) -> bool:
    """True, wenn Thinking fuer diesen Job deaktiviert werden soll (Default: nie)."""
    return bool(job_type and job_type in _THINKING_DISABLED_JOB_TYPES)


# ── Trace-Callbacks (Transparenz) ────────────────────────

def _trace_append(event: dict) -> None:
    if len(_job_trace) < _MAX_TRACE_EVENTS:
        _job_trace.append(event)


def _on_reasoning(text: str) -> None:
    if text:
        _trace_append({"type": "thinking", "text": str(text)[:2000]})


def _on_tool_start(tc_id, name, args) -> None:
    event = {"type": "tool_start", "name": str(name)}
    # Bei Skill-Aufrufen den geladenen Skill-Namen miterfassen (Grundlage fuer
    # die Skill-Nutzungs-Analytics im Intelligenz-Tab). Best-effort -- args kann
    # ein Dict oder ein JSON-String sein.
    if str(name) in ("skill_view", "skill_manage"):
        skill = None
        try:
            if isinstance(args, dict):
                skill = args.get("name") or args.get("skill")
            elif isinstance(args, str) and args.strip().startswith("{"):
                skill = (json.loads(args) or {}).get("name")
        except Exception:  # noqa: BLE001 - Trace darf nie scheitern
            skill = None
        if skill:
            event["skill"] = str(skill)
    _trace_append(event)


def _on_tool_complete(tc_id, name, args, result) -> None:
    _trace_append({"type": "tool_complete", "name": str(name), "result": str(result)[:500]})


# ── Prompt-Bausteine (framework-agnostisch) ──────────────

def _triage_skill_available() -> bool:
    """True, wenn der Hermes-native ``email-triage``-Skill ausgerollt ist."""
    return EMAIL_TRIAGE_SKILL.exists()


def _style_skill_available() -> bool:
    """True, wenn der Hermes-native ``email-style``-Skill ausgerollt ist."""
    return EMAIL_STYLE_SKILL.exists()


def _load_triage_skill() -> str:
    """Datei-Fallback fuer den Triage-Skill (nur falls skill_view scheitert).

    Bevorzugt den nativen Skill (SKILL.md + references), sonst die Legacy-Flat-Datei.
    """
    if EMAIL_TRIAGE_SKILL.exists():
        parts = [EMAIL_TRIAGE_SKILL.read_text(encoding="utf-8")]
        if EMAIL_TRIAGE_REFERENCES.is_dir():
            for ref in sorted(EMAIL_TRIAGE_REFERENCES.glob("*.md")):
                parts.append(f"\n\n---\n\n# {ref.name}\n\n{ref.read_text(encoding='utf-8')}")
        return "".join(parts)
    if LEGACY_TRIAGE_SKILL.exists():
        return LEGACY_TRIAGE_SKILL.read_text(encoding="utf-8")
    logger.warning("Triage-Skill nicht gefunden: %s / %s", EMAIL_TRIAGE_SKILL, LEGACY_TRIAGE_SKILL)
    return ""


def _load_style_profile() -> str:
    """Datei-Fallback fuer den Schreibstil-Kanon (nur falls skill_view scheitert)."""
    if EMAIL_STYLE_SKILL.exists():
        return EMAIL_STYLE_SKILL.read_text(encoding="utf-8")
    if LEGACY_STYLE_PROFILE.exists():
        return LEGACY_STYLE_PROFILE.read_text(encoding="utf-8")
    logger.warning("Schreibstil-Kanon nicht gefunden: %s / %s", EMAIL_STYLE_SKILL, LEGACY_STYLE_PROFILE)
    return ""


async def _load_projects_context() -> str:
    """Laedt alle aktiven Projekte aus der DB und formatiert sie als Prompt-Kontext."""
    async with async_session() as db:
        result = await db.execute(
            select(Project).where(Project.status != "archived").order_by(Project.name)
        )
        projects = list(result.scalars().all())

    if not projects:
        return "## VERFÜGBARE PROJEKTE\nKeine aktiven Projekte vorhanden."

    lines = ["## VERFÜGBARE PROJEKTE", ""]
    for p in projects:
        lines.append(f'- "{p.name}" (id: {p.id})')
    lines.append("")
    lines.append("Wähle bei triage_class='task' das passendste Projekt aus dieser Liste für das Feld suggested_project.")
    lines.append("Falls kein Projekt passt, setze suggested_project auf null.")
    return "\n".join(lines)


async def _build_recall_block(meta: dict) -> str:
    """Few-Shot-Recall: gelernte Lektionen aus aehnlichen frueheren Korrekturen.

    Hoechstes Lernsignal -- zeigt dem Agenten, wie der Berater in vergleichbaren
    Faellen frueher korrigiert hat, damit derselbe Fehler nicht wiederholt wird.
    Best-effort: ohne Embedding-Modell/Episoden faellt der Block weg.
    """
    cfg = get_settings()
    if not cfg.agent_recall_enabled:
        return ""
    try:
        from app.services.learning import recall_similar_episodes

        subject = meta.get("subject", "")
        from_addr = meta.get("from_address", "")
        from_name = meta.get("from_name", "")
        preview = meta.get("body_preview", "")
        query = f"E-Mail von {from_name} <{from_addr}>: '{subject}'. {preview[:300]}"

        async with async_session() as db:
            episodes = await recall_similar_episodes(
                db, query=query, job_type="email_triage", k=3, corrected_only=True,
            )
        lessons = [e for e in episodes if (e.get("lesson") or "").strip()]
        if not lessons:
            return ""

        lines = []
        for e in lessons:
            sim = e.get("similarity")
            sim_pct = f" ({round(float(sim) * 100)}% aehnlich)" if isinstance(sim, (int, float)) else ""
            sender = e.get("sender_email") or "?"
            lines.append(f"- Frueherer Fall ({sender}){sim_pct}: {e['lesson'].strip()}")

        return (
            "\n---\n\n## GELERNTE LEKTIONEN AUS FRÜHEREN KORREKTUREN (BEACHTEN!)\n"
            "Der Berater hat in ähnlichen Fällen früher korrigiert. Wiederhole diese "
            "Fehler NICHT:\n" + "\n".join(lines) + "\n"
        )
    except Exception:  # noqa: BLE001 - best-effort, darf Prompt-Bau nie stoppen
        logger.warning("Recall-Block konnte nicht erzeugt werden")
        return ""


def _compute_self_grade(
    meta: dict, result_meta: dict, tools_used: list[str]
) -> dict:
    """Deterministisches Self-Grading eines Triage-Jobs (Saeule 3).

    Prueft anhand der tatsaechlich aufgerufenen Tools, ob der Agent die im Prompt
    geforderten Pflicht-Kontexte geladen hat (Thread/Absender-History/-Profil) und
    -- bei einem Entwurf -- den Stil-Anker (`search_my_replies`) genutzt hat. Rein
    und damit unabhaengig testbar. Tool-Namen werden per Substring gematcht, um
    MCP-Praefixe abzufangen.
    """

    def used(key: str) -> bool:
        return any(key in (t or "") for t in tools_used)

    has_conversation = bool(meta.get("conversation_id"))
    has_draft = bool(result_meta.get("draft_id"))

    checks: dict[str, bool] = {
        "sender_history_loaded": used("search_sender_history"),
        "sender_profile_loaded": used("get_sender_profile"),
    }
    if has_conversation:
        checks["thread_loaded"] = used("get_thread")
    if has_draft:
        checks["style_anchor_used"] = used("search_my_replies")

    passed = sum(1 for v in checks.values() if v)
    total = len(checks) or 1
    missing = [k for k, v in checks.items() if not v]
    return {
        "score": round(passed / total, 2),
        "checks": checks,
        "missing": missing,
    }


async def _build_active_rules_block() -> str:
    """Vom Berater freigegebene gelernte Regeln (Saeule 5) in den Prompt einspeisen.

    Nur ``status='active'``-Regeln wirken -- Vorschlaege (``proposed``) bleiben bis
    zur HITL-Freigabe folgenlos. Best-effort.
    """
    try:
        from app.models import LearnedRule

        async with async_session() as db:
            result = await db.execute(
                select(LearnedRule)
                .where(
                    LearnedRule.status == "active",
                    LearnedRule.scope.in_(("triage", "draft", "general")),
                )
                .order_by(LearnedRule.approved_at.desc())
                .limit(20)
            )
            rules = result.scalars().all()
        if not rules:
            return ""
        lines = [f"- [{r.scope}] {r.rule_text}" for r in rules]
        return (
            "\n---\n\n## AKTIVE GELERNTE REGELN (vom Berater freigegeben -- VERBINDLICH)\n"
            "Diese Regeln wurden aus deinen frueheren Korrekturen abgeleitet und "
            "freigegeben. Befolge sie:\n" + "\n".join(lines) + "\n"
        )
    except Exception:  # noqa: BLE001 - best-effort
        logger.warning("Aktive-Regeln-Block konnte nicht erzeugt werden")
        return ""


async def _build_triage_prompt(job: AgentJob) -> str:
    """Baut den Prompt für einen email_triage Job aus Metadata.

    Hermes-native: Der Agent laedt den ``email-triage``- und ``email-style``-Skill
    selbst via ``skill_view`` (Progressive Disclosure). Nur falls die nativen Skills
    (noch) nicht auf der Platte liegen, wird der Datei-Inhalt als Fallback injiziert.
    """
    skill_native = _triage_skill_available()
    style_native = _style_skill_available()
    skill_text = "" if skill_native else _load_triage_skill()
    style_text = "" if style_native else _load_style_profile()
    projects_context = await _load_projects_context()

    custom_triage_prompt = ""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(User.settings).where(User.role == "owner").limit(1)
            )
            owner_settings = result.scalar_one_or_none() or {}
        custom_triage_prompt = (owner_settings.get("triage_prompt") or "").strip()
    except Exception:
        logger.warning("Konnte triage_prompt nicht aus User-Settings laden")

    meta = job.metadata_json or {}
    email_id = meta.get("email_message_id", "")
    subject = meta.get("subject", "")
    from_addr = meta.get("from_address", "")
    from_name = meta.get("from_name", "")
    preview = meta.get("body_preview", "")
    inference = meta.get("inference_classification", "")
    conversation_id = meta.get("conversation_id", "")
    recipient_type = meta.get("recipient_type", "unknown")
    forced_class = meta.get("forced_class")
    correction_reason = meta.get("correction_reason") or ""
    recall_block = await _build_recall_block(meta)
    rules_block = await _build_active_rules_block()

    correction_block = ""
    if forced_class:
        artefakt = "einen Antwort-Entwurf (auto_reply)" if forced_class == "auto_reply" else "eine Aufgabe (task)"
        correction_block = (
            "## ⚠️ KORREKTUR DES BERATERS (HÖCHSTE PRIORITÄT)\n\n"
            f"Der Berater hat entschieden: Diese E-Mail MUSS als **{forced_class}** behandelt werden "
            f"-> erzeuge {artefakt}.\n"
            "→ Klassifiziere NICHT neu und überschreibe diese Entscheidung NICHT.\n"
            "→ Lade dennoch die Pflicht-Kontexte (Thread, Absender-History, -Profil) "
            "und nutze bei auto_reply den Stil-Anker (search_my_replies), bevor du den "
            "Artefakt erzeugst.\n"
            f"→ Setze triage_class im JSON-Block zwingend auf \"{forced_class}\".\n"
            + (f"→ Begründung des Beraters: {correction_reason}\n" if correction_reason else "")
            + "\n---\n\n"
        )

    thread_hint = ""
    if conversation_id:
        thread_hint = f"""
**Konversations-ID:** {conversation_id}
→ Lade den Thread mit get_thread("{conversation_id}") für vollständigen Kontext.
→ Lade die Absender-History mit search_sender_history("{from_addr}") um Kommunikationsmuster zu erkennen.
"""

    recipient_hint = ""
    if recipient_type == "cc":
        recipient_hint = (
            "\n⚠️ **ACHTUNG: Anthony ist bei dieser E-Mail NUR im CC, NICHT im TO.**\n"
            "→ Beachte die CC-Regeln (Abschnitt 2 in references/triage-rules.md)!\n"
            "→ Default: triage_class=fyi, KEIN auto_reply, KEIN task — "
            "es sei denn, Anthony wird im Body direkt angesprochen.\n"
        )

    # Skill-Sektion: nativ via skill_view (Default) oder Datei-Fallback.
    if skill_native:
        skill_section = (
            "## TRIAGE-SKILL (NATIV LADEN)\n\n"
            "Du hast einen email_triage Job. Lade ZUERST den Skill und befolge ihn strikt:\n"
            "→ **skill_view(name='email-triage')**\n"
            "Er enthält den vollständigen Ablauf, die Prioritätsstufen, CC-Regeln, die "
            "auto_reply-Schwelle, die Move-Ordner und den Pflicht-JSON-Block. Lies bei "
            "Bedarf die referenzierten Dateien (references/triage-rules.md für Detail-Regeln "
            "und das JSON-Schema, references/examples.md für Entwurfs-Vorbilder)."
        )
    else:
        skill_section = f"## TRIAGE-INSTRUKTIONEN (STRIKT befolgen!)\n\n{skill_text}"

    # Schreibstil-Sektion: nativ via skill_view (Default) oder Datei-Fallback.
    if style_native:
        style_section = (
            "\n---\n\n## SCHREIBSTIL (bei jedem Antwort-Entwurf)\n\n"
            "Bevor du einen auto_reply-Draft formulierst, lade den persönlichen "
            "Schreibstil-Kanon von Anthony und halte dich strikt daran:\n"
            "→ **skill_view(name='email-style')**\n"
        )
    elif style_text:
        style_section = (
            "\n---\n\n## SCHREIBSTIL (VERBINDLICH für jeden Antwort-Entwurf)\n\n"
            "Wenn du einen Draft (auto_reply) formulierst, halte dich strikt an den "
            "folgenden persönlichen Schreibstil-Kanon von Anthony Smith. Ziel: Anthony "
            f"muss sich im Entwurf wiedererkennen.\n\n{style_text}\n"
        )
    else:
        style_section = ""

    return f"""{correction_block}{skill_section}

---

{projects_context}
{recall_block}{rules_block}
---

## AKTUELLER JOB

Du hast einen email_triage Job erhalten. Führe den kompletten Triage-Ablauf gemäss dem email-triage-Skill durch.

**Job-ID:** {job.id}
**E-Mail Message-ID:** {email_id}
**Betreff:** {subject}
**Von:** {from_name} <{from_addr}>
**Empfänger-Typ:** {recipient_type} {"(Anthony ist direkter Empfänger im TO)" if recipient_type == "to" else "(Anthony ist NUR im CC)" if recipient_type == "cc" else "(nicht eindeutig bestimmbar)"}
**Microsoft Inference:** {inference}
**Body-Vorschau:** {preview[:300]}
{recipient_hint}{thread_hint}
{style_section}
## PFLICHT-AUFRUFE VOR JEDER KLASSIFIKATION UND DRAFT-ERSTELLUNG

Du MUSST die folgenden drei Kontext-Quellen laden, BEVOR du klassifizierst oder einen Draft erstellst:
1. **get_thread("{conversation_id or ''}")** -- Thread-Kontext laden (PFLICHT falls conversation_id vorhanden)
2. **search_sender_history("{from_addr}")** -- Absender-History laden (IMMER PFLICHT)
3. **get_sender_profile("{from_addr}")** -- Absender-Profil laden (IMMER PFLICHT)

Erstelle NIEMALS einen Draft ohne diese drei Kontext-Quellen geladen zu haben!

---

WICHTIG: Befolge die Prioritätsreihenfolge (Stufe 1 → Stufe 2 → Stufe 3) STRIKT.
- Prüfe ZUERST ob Stufe 1 (Signale) zutrifft.
- Prüfe DANN ob Stufe 2 (System) zutrifft.
- Nur wenn weder Stufe 1 noch 2 passen, wende Stufe 3 (Standardregeln) an.

Führe jetzt den Triage-Ablauf durch:
1. Lies die E-Mail mit get_email("{email_id}"). Falls hasAttachments=true und Bildinhalt für die Einordnung relevant sein könnte (Screenshot, gescanntes Dokument, Bild-Newsletter), rufe get_email_attachments("{email_id}") auf und werte jeden Bild-Anhang mit vision_analyze(image_url=<path>, user_prompt="Beschreibe den Inhalt für die E-Mail-Triage") aus.
2. Lies die Kategorien mit get_email_categories("{email_id}")
3. Lade Thread-Kontext, Absender-History und Absender-Profil (PFLICHT!)
4. Klassifiziere gemäss der Prioritätsreihenfolge
5. Setze die Outlook-Kategorie
6. Verschiebe bei Bedarf (System/Newsletter/Junk/Kalender)
7. Erstelle Draft falls auto_reply. WICHTIG: Rufe VORHER search_my_replies("{from_addr}") auf und nutze die letzten von Anthony gesendeten Antworten an diesen Kontakt als VERBATIM Stil-Anker (imitiere Ton, Länge, Anrede und Schlussformel). PFLICHT: Übergib bei create_draft IMMER reply_to_id="{email_id}", damit die Antwort im selben Thread landet (NIEMALS einen neuen Thread starten). Empfänger NICHT manuell überschreiben — createReply setzt den korrekten Empfänger automatisch. (Bei task übernimmt das Backend die Task-Erstellung automatisch.)
8. Gib den PFLICHT-JSON-Block aus (Schema im Skill bzw. references/triage-rules.md)
9. Aktualisiere das Absender-Profil mit update_sender_profile (siehe Skill)
10. Melde das Ergebnis mit update_agent_job("{job.id}", status="completed"|"awaiting_approval", output="...")
""" + (f"\n\n## ZUSÄTZLICHE BENUTZER-REGELN (haben Vorrang!)\n{custom_triage_prompt}" if custom_triage_prompt else "")


async def _build_chat_triage_prompt(job: AgentJob) -> str:
    """Baut den Prompt für einen chat_triage Job mit Kontext."""
    meta = job.metadata_json or {}
    chat_id = meta.get("chat_id", "")
    message_id = meta.get("chat_message_id", "")
    sender = meta.get("sender_name", "")
    preview = meta.get("body_preview", "")

    projects_context = await _load_projects_context()

    return f"""## CHAT-TRIAGE JOB

Du hast eine neue Microsoft Teams Chat-Nachricht erhalten. Analysiere und klassifiziere sie.

{projects_context}

**Job-ID:** {job.id}
**Chat-ID:** {chat_id}
**Nachricht-ID:** {message_id}
**Absender:** {sender}
**Vorschau:** {preview[:300]}

## VORGEHEN

1. Lies die vollständige Nachricht mit den verfügbaren MCP-Tools
2. Klassifiziere: Ist die Nachricht eine Aufgabe (task), eine reine Information (fyi), oder eine Meeting-Transkript-Benachrichtigung?
3. Bei task: Erstelle einen TaskPilot-Task mit Kontext-Briefing und passendem Projekt
4. Bei fyi: Nur zur Kenntnis nehmen
5. Melde das Ergebnis mit update_agent_job("{job.id}", status="completed", output="...")
"""


async def _build_generic_prompt(job: AgentJob) -> str:
    """Baut einen kontextreichen Prompt für generische AgentJobs."""
    meta = job.metadata_json or {}
    projects_context = await _load_projects_context()

    skill_hint = ""
    skill_name = meta.get("skill")
    canonical_skill = _SKILL_NAME_ALIASES.get(skill_name, skill_name) if skill_name else None
    if canonical_skill:
        native_path = HERMES_HOME / "skills" / canonical_skill / "SKILL.md"
        legacy_path = HERMES_HOME / "skills" / f"{skill_name}.md"
        if native_path.exists():
            # Hermes-native: Agent laedt den Skill selbst (Progressive Disclosure).
            skill_hint = (
                f"\n## SKILL (NATIV LADEN)\n\nLade zuerst den Skill und befolge ihn strikt:\n"
                f"→ **skill_view(name='{canonical_skill}')**\n"
            )
        elif legacy_path.exists():
            skill_hint = f"\n## SKILL-INSTRUKTIONEN\n\n{legacy_path.read_text(encoding='utf-8')}\n"

    style_hint = ""
    if canonical_skill in ("quick-response", "email-triage"):
        if _style_skill_available():
            style_hint = (
                "\n## SCHREIBSTIL (bei jedem Antwort-Entwurf)\n\n"
                "Bevor du einen Antwort-Entwurf formulierst, lade den persönlichen "
                "Schreibstil-Kanon: → **skill_view(name='email-style')**\n"
            )
        else:
            style_text = _load_style_profile()
            if style_text:
                style_hint = (
                    "\n## SCHREIBSTIL (VERBINDLICH für jeden Antwort-Entwurf)\n\n"
                    "Halte dich strikt an den folgenden persönlichen Schreibstil-Kanon "
                    "von Anthony Smith. Ziel: Anthony muss sich im Entwurf wiedererkennen.\n\n"
                    f"{style_text}\n"
                )

    description = meta.get("description", meta.get("prompt", str(meta)))

    return f"""## AGENT-JOB

{projects_context}
{skill_hint}{style_hint}

**Job-ID:** {job.id}
**Job-Typ:** {job.job_type or 'generic'}
**Auftrag:** {description}

Führe den Auftrag aus und melde das Ergebnis mit update_agent_job("{job.id}", status="completed", output="...").
"""


# ── Post-Processing (framework-agnostisch) ───────────────

def _extract_json_block(content: str) -> dict | None:
    """Extrahiert den JSON-Block aus dem LLM-Output."""
    pattern = r"```json\s*\n(.*?)\n\s*```"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("JSON-Block gefunden aber nicht parsebar: %s", match.group(1)[:200])
            return None

    json_pattern = r"\{[^{}]*\"label\"[^{}]*\"triage_class\"[^{}]*\}"
    matches = list(re.finditer(json_pattern, content, re.DOTALL))
    if matches:
        try:
            return json.loads(matches[-1].group(0))
        except json.JSONDecodeError:
            return None

    return None


def _match_project(suggested_name: str | None, projects: list) -> tuple | None:
    """Matched einen Projektnamen gegen die DB-Projekte (case-insensitive contains)."""
    if not suggested_name or not projects:
        return None
    name_lower = suggested_name.lower()
    for p in projects:
        if name_lower in p.name.lower() or p.name.lower() in name_lower:
            return p
    return None


def _determine_pipeline_column(deadline_str: str | None) -> str | None:
    """Bestimmt die Pipeline-Spalte basierend auf der Deadline."""
    if not deadline_str:
        return PIPELINE_COLUMNS["this_week"]
    try:
        deadline = date.fromisoformat(deadline_str)
    except ValueError:
        return PIPELINE_COLUMNS["this_week"]

    today = date.today()
    delta = (deadline - today).days

    if delta <= 1:
        return PIPELINE_COLUMNS["focus"]
    if delta <= 7:
        return PIPELINE_COLUMNS["this_week"]
    if delta <= 14:
        return PIPELINE_COLUMNS["next_week"]
    return PIPELINE_COLUMNS["this_month"]


async def _build_graph_client():
    """Baut einen GraphClient aus den Settings (oder None, wenn nicht konfiguriert)."""
    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        return None
    import sys as _sys

    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
    from graph_client import GraphClient, GraphConfig  # noqa: E402

    return GraphClient(GraphConfig(
        tenant_id=s.graph_tenant_id,
        client_id=s.graph_client_id,
        client_secret=s.graph_client_secret,
        user_email=s.graph_user_email,
    ))


async def _snapshot_agent_draft(draft_id: str) -> dict | None:
    """Liest den vom Agenten erstellten Entwurf (Body + Empfaenger + conversationId).

    Dient als Original-Referenz fuer den spaeteren Stil-Diff (Lernsignal). Best-effort.
    """
    client = await _build_graph_client()
    if client is None:
        return None
    try:
        msg = await client.get_email(draft_id)
        body = msg.get("body", {}) or {}
        return {
            "body_html": body.get("content") if body.get("contentType") == "html" else msg.get("bodyPreview"),
            "conversation_id": msg.get("conversationId"),
            "to": [r.get("emailAddress", {}).get("address", "") for r in msg.get("toRecipients", [])],
            "cc": [r.get("emailAddress", {}).get("address", "") for r in msg.get("ccRecipients", [])],
        }
    except Exception:  # noqa: BLE001 - best-effort, darf Job nicht stoppen
        logger.warning("Draft-Snapshot fehlgeschlagen (draft_id=%s)", str(draft_id)[:40])
        return None
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001
            pass


async def _post_process_triage(job_id, content: str, meta: dict) -> str:
    """Deterministische Post-Processing-Logik nach LLM-Klassifikation."""
    parsed = _extract_json_block(content)
    if parsed is None:
        logger.warning("Job %s: Kein JSON-Block im Output gefunden", job_id)
        return "completed"

    triage_class = parsed.get("triage_class")
    label = parsed.get("label")
    draft_id = parsed.get("draft_id")
    deadline = parsed.get("deadline")
    task_title = parsed.get("task_title")
    task_description = parsed.get("task_description")
    suggested_project = parsed.get("suggested_project")
    rationale = parsed.get("rationale")
    reply_expected = bool(parsed.get("reply_expected", False))

    if triage_class == "quick_response":
        triage_class = "auto_reply"
    elif triage_class == "board_task":
        triage_class = "task"
        reply_expected = True
    elif triage_class == "bedenkzeit":
        triage_class = "task"

    # Berater-Korrektur erzwingen: Eine vom Menschen vorgegebene Klasse hat Vorrang
    # vor der (ggf. abweichenden) Selbst-Klassifikation des Agenten.
    forced_class = meta.get("forced_class")
    if forced_class in ("auto_reply", "task", "fyi") and triage_class != forced_class:
        logger.info(
            "Job %s: forced_class=%s erzwingt Korrektur (Agent wollte %s)",
            job_id, forced_class, triage_class,
        )
        triage_class = forced_class

    # Bei erzwungener Klasse den Draft-basierten Auto-Switch unterdruecken, damit
    # eine bewusst gewollte 'task'-Korrektur nicht zurueck auf auto_reply kippt.
    if draft_id and triage_class != "auto_reply" and forced_class != "task":
        logger.warning("Job %s: draft_id vorhanden aber triage_class=%s, korrigiere zu auto_reply", job_id, triage_class)
        triage_class = "auto_reply"

    if triage_class == "auto_reply" and not draft_id:
        logger.warning("Job %s: auto_reply ohne draft_id, Fallback auf task", job_id)
        triage_class = "task"
        if not task_title:
            task_title = meta.get("subject", "E-Mail Triage")

    if triage_class == "task" and not task_title:
        task_title = meta.get("subject", "E-Mail Triage (kein Titel)")
        logger.warning("Job %s: task ohne task_title, verwende Subject: %s", job_id, task_title)

    logger.info(
        "Job %s: JSON parsed -- label=%s, triage_class=%s, reply_expected=%s, draft_id=%s",
        job_id, label, triage_class, reply_expected, draft_id,
    )

    async with async_session() as db:
        await db.execute(
            update(EmailTriage)
            .where(EmailTriage.agent_job_id == job_id)
            .values(
                triage_class=triage_class,
                reply_expected=reply_expected,
                suggested_action={
                    "label": label,
                    "triage_class": triage_class,
                    "reply_expected": reply_expected,
                    "deadline": deadline,
                    "task_title": task_title,
                    "suggested_project": suggested_project,
                    "draft_id": draft_id,
                    "rationale": rationale,
                },
                status="acted" if triage_class != "auto_reply" else "processing",
            )
        )

        final_status = "completed"

        if triage_class == "task" and task_title:
            proj_result = await db.execute(
                select(Project).where(Project.status != "archived").order_by(Project.name)
            )
            projects = list(proj_result.scalars().all())
            matched_project = _match_project(suggested_project, projects)
            if not matched_project and projects:
                matched_project = projects[0]

            if matched_project:
                col_result = await db.execute(
                    select(BoardColumn)
                    .where(BoardColumn.project_id == matched_project.id)
                    .order_by(BoardColumn.position)
                    .limit(1)
                )
                first_col = col_result.scalar_one_or_none()

                if first_col:
                    pipeline_col_id = _determine_pipeline_column(deadline)
                    email_message_id = meta.get("email_message_id")
                    email_conversation_id = meta.get("conversation_id")

                    due_date = None
                    if deadline:
                        try:
                            due_date = date.fromisoformat(deadline)
                        except ValueError:
                            pass

                    max_pos_result = await db.execute(
                        select(Task.board_position)
                        .where(Task.board_column_id == first_col.id)
                        .order_by(Task.board_position.desc())
                        .limit(1)
                    )
                    max_pos_row = max_pos_result.scalar_one_or_none()
                    next_pos = (max_pos_row or 0) + 1

                    new_task = Task(
                        title=task_title,
                        description=task_description or f"Erstellt aus E-Mail: {meta.get('subject', '')}",
                        project_id=matched_project.id,
                        board_column_id=first_col.id,
                        board_position=next_pos,
                        pipeline_column_id=pipeline_col_id,
                        email_message_id=email_message_id,
                        email_conversation_id=email_conversation_id,
                        due_date=due_date,
                        needs_review=True,
                        assignee="me",
                    )
                    db.add(new_task)
                    await db.flush()
                    await notify_task_suggested(
                        db,
                        task_id=new_task.id,
                        task_title=task_title,
                        from_email=meta.get("from_address"),
                    )
                    logger.info(
                        "Job %s: Task erstellt '%s' in Projekt '%s' (reply_expected=%s)",
                        job_id, task_title, matched_project.name, reply_expected,
                    )

        elif triage_class == "auto_reply" and draft_id:
            job_result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
            job = job_result.scalar_one_or_none()
            if job:
                existing_meta = dict(job.metadata_json or {})
                existing_meta["draft_id"] = draft_id
                # Original-Entwurf als Referenz fuer den spaeteren Stil-Diff snapshotten.
                snapshot = await _snapshot_agent_draft(draft_id)
                if snapshot:
                    existing_meta["original_draft_html"] = snapshot.get("body_html")
                    existing_meta["draft_conversation_id"] = snapshot.get("conversation_id")
                    existing_meta["draft_to"] = snapshot.get("to")
                    existing_meta["draft_cc"] = snapshot.get("cc")
                job.metadata_json = existing_meta
            final_status = "awaiting_approval"
            await notify_agent_awaiting_approval(
                db, job_id=job_id, subject=meta.get("subject"),
            )

        # Episode fuer das episodische Gedaechtnis ablegen (Recall-Basis).
        if triage_class:
            from_name = meta.get("from_name") or ""
            from_address = meta.get("from_address") or ""
            subject = meta.get("subject") or "(kein Betreff)"
            summary = (
                f"E-Mail von {from_name} <{from_address}>: '{subject}'. "
                f"Triage-Entscheid: {triage_class}"
                + (", Antwort erwartet" if reply_expected else "")
            )
            await record_episode(
                db,
                summary=summary,
                job_type="email_triage",
                agent_job_id=job_id,
                sender_email=from_address or None,
                decision={
                    "triage_class": triage_class,
                    "reply_expected": bool(reply_expected),
                    "draft_id": draft_id,
                },
            )

        await db.commit()

    return final_status


# ── Runtime-Initialisierung ──────────────────────────────

def _is_local_model(sel: str) -> bool:
    """True, wenn das Modell lokal ueber Ollama laeuft (Default oder ``ollama/*``)."""
    return not sel or sel in ("nanobot", "hermes") or sel.startswith("ollama/")


# Cloud-Provider (z. B. OpenAI) begrenzen die Anzahl Tools pro Request auf 128.
# Lokales Ollama kennt dieses Limit nicht. Gilt als Sicherheitsnetz fuer den
# Cloud-Pfad (aktuell 113 MCP-Tools insgesamt, also unkritisch).
CLOUD_TOOL_LIMIT = 128


def get_configured_server_keys() -> list[str]:
    """Liest die konfigurierten MCP-Server-Keys aus ``~/.hermes/config.yaml``.

    Die Keys (z. B. ``graph``, ``bexio``) sind zugleich die Hermes-Toolset-Aliase
    (``validate_toolset`` akzeptiert Aliase), die in ``enabled_toolsets`` genutzt
    werden, um einzelne MCP-Server gezielt freizugeben.
    """
    import yaml

    config_path = HERMES_HOME / "config.yaml"
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return list((config.get("mcp_servers") or {}).keys())
    except Exception:
        logger.exception("MCP-Server-Keys konnten nicht aus config.yaml gelesen werden")
        return []


def resolve_cloud_toolsets(enabled_servers: list[str] | None) -> list[str]:
    """Validiert die gewuenschten MCP-Server gegen die Konfiguration.

    Gibt die Toolset-Namen (= Server-Aliase) zurueck, die fuer ein Cloud-Modell
    freigegeben werden. Unbekannte/nicht konfigurierte Server werden verworfen.
    Eine leere Liste bedeutet Default-Deny (keine MCP-Tools).
    """
    configured = set(get_configured_server_keys())
    return [s for s in (enabled_servers or []) if s in configured]


# Kuratierte Allowlist der Hermes-Core-Toolsets fuer lokale Agenten (Worker + Chat).
# Bewusst OHNE rohe Host-Ausfuehrung: KEIN terminal/process, KEIN file-write,
# KEIN browser, KEIN execute_code (Host), KEIN delegation/messaging/cronjob/
# image_gen/tts/homeassistant/rl. Riskante bzw. ausfuehrende Aktionen laufen
# ausschliesslich ueber die gekapselten MCP-Server (scripts = registrierte Docker-
# Scripts, sandbox = isolierter Docker) mit HITL-Gate. So bleibt die Sandbox-/
# No-Host-Execution-Philosophie gewahrt, waehrend die agentischen Faehigkeiten
# (Wissen, Lernen, Recall, Rueckfragen, Vision, Web-Recherche) voll nutzbar sind.
LOCAL_CORE_TOOLSETS: list[str] = [
    "skills",          # skills_list, skill_view, skill_manage
    "memory",          # memory: deklaratives Langzeitwissen schreiben/lesen
    "session_search",  # frühere Gespräche durchsuchen (Kontinuität)
    "clarify",         # strukturierte HITL-Rückfragen
    "todo",            # Mehrschritt-Planung
    "vision",          # vision_analyze: E-Mail-Anhänge/Screenshots verstehen
    "web",             # web_search + web_extract: agentische Recherche (statt Eigenbau)
]

# Fallback-Server-Keys, falls config.yaml (noch) nicht lesbar ist. Deckt sich mit
# build_config_dict() in hermes_config.py.
_KNOWN_MCP_SERVERS: list[str] = [
    "taskpilot", "graph", "pipedrive", "toggl", "bexio",
    "signa", "invoiceinsight", "scripts", "sandbox", "contentConverter",
]


def build_local_allowlist(include_delegation: bool = False) -> list[str]:
    """Allowlist fuer lokale Agenten: kuratierte Core-Toolsets + konfigurierte MCP-Server.

    ``include_delegation`` aktiviert das ``delegation``-Toolset (``delegate_task``):
    nur fuer den interaktiven Chat-Agenten (InnoPilot) gedacht, der Research-/
    Dokument-Jobs in Subagenten zerlegen kann. Subagenten erben dieselbe gehaertete
    Allowlist (kein Host-Shell), und externe Ausgaben bleiben HITL-pflichtig. Der
    fokussierte Triage-Worker bekommt KEINE Delegation (kein Subagenten-Spawn).

    Ersetzt das fruehere ``enabled_toolsets=None`` (volles Core-Toolkit inkl. Host-
    Shell). Die MCP-Server-Keys sind zugleich Toolset-Aliase (siehe
    ``resolve_cloud_toolsets``); fehlt die Config, greift ``_KNOWN_MCP_SERVERS``.
    """
    servers = get_configured_server_keys() or _KNOWN_MCP_SERVERS
    core = [*LOCAL_CORE_TOOLSETS, "delegation"] if include_delegation else LOCAL_CORE_TOOLSETS
    return [*core, *servers]


def count_tools(enabled_toolsets: list[str] | None) -> int:
    """Anzahl der Tool-Definitionen fuer eine gegebene Toolset-Auswahl.

    Setzt eine erfolgte MCP-Discovery (``ensure_runtime_ready``) voraus.
    """
    try:
        from model_tools import get_tool_definitions

        return len(get_tool_definitions(enabled_toolsets=enabled_toolsets, quiet_mode=True))
    except Exception:
        logger.exception("Tool-Anzahl konnte nicht ermittelt werden")
        return 0


def _build_worker_agent():
    """Konstruiert den persistenten Worker-AIAgent (laeuft im Thread)."""
    from run_agent import AIAgent

    cfg = get_settings()
    model = cfg.triage_model.removeprefix("ollama/")
    # Worker nutzt per Default ein lokales Modell (voller Zugriff). Falls jemand
    # ein Cloud-Triage-Modell konfiguriert, gilt Default-Deny wie im Chat:
    # keine MCP-Tools, kein Memory/USER-Profil, keine Kontextdateien.
    if _is_local_model(cfg.triage_model):
        base_url = f"{cfg.ollama_base_url.rstrip('/')}/v1"
        api_key = "ollama"
        # Härtung: explizite Allowlist statt None (= volles Host-Toolkit).
        enabled_toolsets = build_local_allowlist()
        skip_memory = False
        skip_context_files = False
    else:
        base_url = f"{cfg.litellm_base_url.rstrip('/')}/v1"
        api_key = "sk-litellm-local"
        model = cfg.triage_model
        enabled_toolsets = []
        skip_memory = True
        skip_context_files = True

    return AIAgent(
        base_url=base_url,
        api_key=api_key,
        provider="custom",
        api_mode="chat_completions",
        model=model,
        enabled_toolsets=enabled_toolsets,
        skip_memory=skip_memory,
        skip_context_files=skip_context_files,
        max_iterations=90,
        tool_delay=0.0,
        quiet_mode=True,
        # Hermes-native: Trajektorien persistieren (Grundlage fuer Inspektion +
        # spaeteres Fine-Tuning/Lernen). Best-effort in Hermes, schreibt JSONL.
        save_trajectories=True,
        session_id="taskpilot-worker",
        reasoning_callback=_on_reasoning,
        tool_start_callback=_on_tool_start,
        tool_complete_callback=_on_tool_complete,
    )


async def ensure_runtime_ready() -> bool:
    """Stellt sicher, dass Config geschrieben, Env gesetzt und MCP-Tools registriert sind.

    Idempotent — wird von Worker und Chat-Agent genutzt. Gibt True zurueck, wenn
    die Runtime bereit ist.
    """
    global _runtime_ready
    if _runtime_ready:
        return True

    async with _get_runtime_lock():
        if _runtime_ready:
            return True

        os.environ["HERMES_HOME"] = str(HERMES_HOME)
        try:
            write_hermes_config()
            await populate_hermes_env()
        except Exception:
            logger.exception("Hermes-Config/Env konnte nicht vorbereitet werden")
            return False

        # Trajektorien an definierten Ort buendeln (nach Config, vor Agent-Bau).
        _install_trajectory_path_shim()

        try:
            from tools.mcp_tool import discover_mcp_tools

            tool_names = await asyncio.to_thread(discover_mcp_tools)
            logger.info("Hermes MCP-Discovery: %d Tools registriert", len(tool_names or []))
        except Exception:
            logger.exception("Hermes MCP-Discovery fehlgeschlagen")
            return False

        _runtime_ready = True
        return True


def build_chat_agent(
    model: str | None,
    *,
    enabled_servers: list[str] | None = None,
    include_memory: bool = False,
    on_text=None,
    on_reasoning=None,
    on_tool_start=None,
    on_tool_complete=None,
    clarify_callback=None,
    session_id: str | None = None,
):
    """Konstruiert einen AIAgent fuer den interaktiven Chat (InnoPilot).

    Jede Chat-Anfrage bekommt eine eigene Instanz mit eigenen Callbacks
    (Streaming + Thinking + Tools), damit parallele Anfragen sich nicht
    gegenseitig stoeren. MCP-Tools stammen aus der globalen Registry
    (``ensure_runtime_ready`` muss vorher gelaufen sein).

    Modell-Routing: ``ollama/*`` (und Default) -> Ollama ``/v1`` lokal;
    Cloud-Modelle (``openai/*``, ``anthropic/*``, ``gemini/*``) -> LiteLLM-Proxy.

    Grounding-Politik (Datenschutz):
    - Lokales Modell: voller Zugriff (alle MCP-Tools, Memory/USER-Profil,
      Kontextdateien). Daten bleiben lokal.
    - Cloud-Modell: Default-Deny. Nur explizit per ``enabled_servers``
      freigegebene MCP-Server sind verfuegbar; Memory/USER-Profil nur bei
      ``include_memory=True``; Kontextdateien (SOUL/AGENTS) bleiben aus.
    """
    from run_agent import AIAgent

    cfg = get_settings()
    sel = (model or "").strip()
    if _is_local_model(sel):
        base_url = f"{cfg.ollama_base_url.rstrip('/')}/v1"
        api_key = "ollama"
        resolved_model = sel.removeprefix("ollama/") or cfg.triage_model.removeprefix("ollama/")
        # Lokal: voller Kontext, gehärtete Allowlist + Delegation (Research/Dokument-Subagenten).
        enabled_toolsets = build_local_allowlist(include_delegation=True)
        skip_memory = False
        skip_context_files = False
    else:
        base_url = f"{cfg.litellm_base_url.rstrip('/')}/v1"
        api_key = "sk-litellm-local"
        resolved_model = sel
        # Cloud: Default-Deny, nur explizit freigegebene MCP-Server.
        enabled_toolsets = resolve_cloud_toolsets(enabled_servers)
        skip_memory = not include_memory
        skip_context_files = True

    return AIAgent(
        base_url=base_url,
        api_key=api_key,
        provider="custom",
        api_mode="chat_completions",
        model=resolved_model,
        enabled_toolsets=enabled_toolsets,
        skip_memory=skip_memory,
        skip_context_files=skip_context_files,
        max_iterations=90,
        tool_delay=0.0,
        quiet_mode=True,
        save_trajectories=True,
        session_id=session_id or "taskpilot-chat",
        stream_delta_callback=on_text,
        reasoning_callback=on_reasoning,
        tool_start_callback=on_tool_start,
        tool_complete_callback=on_tool_complete,
        clarify_callback=clarify_callback,
    )


async def _init_agent():
    """Initialisiert den persistenten Worker-Agent (nach Runtime-Setup)."""
    global _agent
    if _agent is not None:
        return _agent
    if not await ensure_runtime_ready():
        return None
    try:
        _agent = await asyncio.to_thread(_build_worker_agent)
        logger.info("Hermes Worker-AIAgent initialisiert (Modell: %s)", _agent.model)
    except Exception:
        logger.exception("Hermes Worker-AIAgent-Initialisierung fehlgeschlagen")
        _agent = None
    return _agent


def _run_agent_sync(agent, prompt: str, disable_thinking: bool) -> str:
    """Synchroner Agent-Lauf (im Thread). Gibt den finalen Antworttext zurueck.

    ``disable_thinking`` setzt SOTA-korrekt ``extra_body.chat_template_kwargs``;
    standardmaessig False (Thinking an).
    """
    prev_overrides = getattr(agent, "request_overrides", None)
    if disable_thinking:
        agent.request_overrides = {
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}
        }
    try:
        result = agent.run_conversation(prompt, system_message=WORKER_SYSTEM_PROMPT)
    finally:
        if disable_thinking:
            agent.request_overrides = prev_overrides

    if isinstance(result, dict):
        return str(result.get("final_response") or "")
    return str(result or "")


async def _process_job(agent, job_id, job_type: str, prompt: str, meta: dict) -> None:
    """Verarbeitet einen einzelnen AgentJob via Hermes AIAgent."""
    global _job_trace
    logger.info("Starte Job %s (type=%s)", job_id, job_type)

    async with async_session() as db:
        await db.execute(
            update(AgentJob)
            .where(AgentJob.id == job_id)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await db.commit()

    _job_trace = []
    disable_thinking = _thinking_disabled(job_type, meta.get("skill"))

    try:
        content = await asyncio.to_thread(_run_agent_sync, agent, prompt, disable_thinking)
        trace = list(_job_trace)
        logger.info("Job %s abgeschlossen: %s", job_id, content[:200])

        if job_type == "email_triage":
            status = await _post_process_triage(job_id, content, meta)
        else:
            status = "completed"
            if "awaiting_approval" in content.lower():
                status = "awaiting_approval"

        if status == "awaiting_approval" and job_type != "email_triage":
            async with async_session() as notif_db:
                await notify_agent_awaiting_approval(notif_db, job_id=job_id)
                await notif_db.commit()

        tools_used = sorted({e["name"] for e in trace if e.get("type") == "tool_start"})
        async with async_session() as db:
            job_result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
            job = job_result.scalar_one_or_none()
            new_meta = dict((job.metadata_json if job else None) or meta)
            new_meta["trace"] = trace
            new_meta["tools_used"] = tools_used
            if job_type == "email_triage":
                grade = _compute_self_grade(meta, new_meta, tools_used)
                new_meta["self_grade"] = grade
                if grade["missing"]:
                    logger.info(
                        "Job %s Self-Grade %.2f, fehlende Pflicht-Kontexte: %s",
                        job_id, grade["score"], grade["missing"],
                    )
            await db.execute(
                update(AgentJob)
                .where(AgentJob.id == job_id)
                .values(
                    status=status,
                    output=content[:4000],
                    metadata_json=new_meta,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    except Exception as e:
        logger.exception("Job %s fehlgeschlagen", job_id)
        async with async_session() as db:
            await db.execute(
                update(AgentJob)
                .where(AgentJob.id == job_id)
                .values(
                    status="failed",
                    error_message=str(e)[:2000],
                    completed_at=datetime.now(timezone.utc),
                )
            )
            if job_type == "email_triage":
                await db.execute(
                    update(EmailTriage)
                    .where(EmailTriage.agent_job_id == job_id)
                    .values(status="dismissed")
                )
            await db.commit()


# ── Wartung (framework-agnostisch) ───────────────────────

async def _cleanup_orphaned_drafts() -> int:
    """Schliesst awaiting_approval-Jobs ab, deren Draft in Outlook nicht mehr existiert."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
    from graph_client import GraphClient, GraphConfig

    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        return 0

    async with async_session() as db:
        result = await db.execute(
            select(AgentJob).where(
                AgentJob.status == "awaiting_approval",
                AgentJob.job_type.in_(["email_triage", "send_email"]),
            )
        )
        jobs = list(result.scalars().all())

    if not jobs:
        return 0

    config = GraphConfig(
        tenant_id=s.graph_tenant_id,
        client_id=s.graph_client_id,
        client_secret=s.graph_client_secret,
        user_email=s.graph_user_email,
    )
    client = GraphClient(config)
    resolved = 0

    try:
        for job in jobs:
            meta = job.metadata_json or {}
            draft_id = meta.get("draft_id")
            if not draft_id:
                continue
            try:
                await client.get_email(draft_id)
            except Exception:
                async with async_session() as db:
                    await db.execute(
                        update(AgentJob)
                        .where(AgentJob.id == job.id)
                        .values(
                            status="completed",
                            output=(job.output or "") + "\n\n--- Entwurf wurde in Outlook gesendet oder gelöscht. Job automatisch abgeschlossen. ---",
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    await db.commit()
                resolved += 1
                logger.info("Draft-Cleanup: Job %s automatisch abgeschlossen (Draft nicht mehr in Outlook)", job.id)
    finally:
        await client.close()

    if resolved:
        logger.info("Draft-Cleanup: %d verwaiste Jobs abgeschlossen", resolved)
    return resolved


async def _reap_stale_jobs() -> int:
    """Setzt running-Jobs, die länger als STALE_TIMEOUT_MINUTES laufen, auf failed."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_TIMEOUT_MINUTES)
    async with async_session() as db:
        result = await db.execute(
            update(AgentJob)
            .where(
                AgentJob.status == "running",
                AgentJob.started_at < cutoff,
            )
            .values(
                status="failed",
                error_message=f"Timeout: Job lief über {STALE_TIMEOUT_MINUTES} Minuten ohne Abschluss",
                completed_at=datetime.now(timezone.utc),
            )
            .returning(AgentJob.id)
        )
        reaped_ids = result.scalars().all()
        if reaped_ids:
            logger.warning(
                "Reaper: %d stale running-Jobs auf failed gesetzt: %s",
                len(reaped_ids), [str(i) for i in reaped_ids],
            )
        await db.commit()
    return len(reaped_ids)


# ── Worker-Loop ──────────────────────────────────────────

async def _worker_loop() -> None:
    """Pollt nach queued Jobs und verarbeitet sie sequentiell."""
    await asyncio.sleep(3)

    agent = await _init_agent()
    if agent is None:
        logger.error("Hermes-Worker kann nicht starten (Runtime nicht verfügbar)")
        return

    logger.info("Hermes-Worker gestartet -- pollt alle %ds nach queued Jobs", POLL_INTERVAL)

    last_reap = time.monotonic()
    last_draft_cleanup = time.monotonic()

    while True:
        try:
            if time.monotonic() - last_reap >= REAP_INTERVAL:
                await _reap_stale_jobs()
                last_reap = time.monotonic()

            if time.monotonic() - last_draft_cleanup >= DRAFT_CLEANUP_INTERVAL:
                try:
                    await _cleanup_orphaned_drafts()
                except Exception:
                    logger.exception("Draft-Cleanup fehlgeschlagen")
                last_draft_cleanup = time.monotonic()

            async with async_session() as db:
                result = await db.execute(
                    select(AgentJob)
                    .where(AgentJob.status == "queued")
                    .order_by(AgentJob.created_at)
                    .limit(1)
                )
                job = result.scalar_one_or_none()

            if job is not None:
                meta = job.metadata_json or {}
                if job.job_type == "email_triage":
                    prompt = await _build_triage_prompt(job)
                elif job.job_type == "chat_triage":
                    prompt = await _build_chat_triage_prompt(job)
                else:
                    prompt = await _build_generic_prompt(job)

                await _process_job(agent, job.id, job.job_type or "generic", prompt, meta)
            else:
                await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Hermes-Worker: unerwarteter Fehler")
            await asyncio.sleep(POLL_INTERVAL)


async def start_hermes_worker() -> None:
    """Startet den Hermes-Worker als Hintergrund-Task."""
    global _worker_task
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("Hermes-Worker: Hintergrund-Task gestartet")


async def stop_hermes_worker() -> None:
    """Stoppt den Hermes-Worker und gibt MCP-Verbindungen frei."""
    global _worker_task, _agent
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    _worker_task = None
    _agent = None
    try:
        from tools.mcp_tool import shutdown_mcp_servers

        await asyncio.to_thread(shutdown_mcp_servers)
    except Exception:
        logger.warning("MCP-Server-Shutdown fehlgeschlagen (ignoriert)")
    logger.info("Hermes-Worker gestoppt")

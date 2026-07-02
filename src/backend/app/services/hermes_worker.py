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

import ast
import asyncio
import json
import logging
import os
import re
import time

import httpx
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import async_session
from app.models import (
    AgentFeedback,
    AgentJob,
    BoardColumn,
    ChatTriage,
    ChecklistItem,
    EmailTriage,
    Project,
    Task,
    User,
)
from app.services.hermes_config import (
    get_hermes_home,
    populate_hermes_env,
    write_hermes_config,
)
from app.services.learning import record_episode
from app.services.notification import (
    notify_agent_awaiting_approval,
    notify_agent_completed,
    notify_task_suggested,
)

logger = logging.getLogger("taskpilot.hermes_worker")

POLL_INTERVAL = 10
REAP_INTERVAL = 60
DRAFT_CLEANUP_INTERVAL = 300  # 5 Minuten
RESWEEP_INTERVAL = 3600  # 60 Minuten: still durchgefallene Triages erneut einreihen
STALE_TIMEOUT_MINUTES = 30
# Maximale Anzahl automatischer Re-Triagen pro E-Mail (verhindert Endlosschleifen).
MAX_RESWEEP = 2
# Nur frische Mails resweepen. Aeltere Mails sind im Postfach oft verschoben/geloescht
# (-> get_email 404) und erzeugten nur Churn + "neue" Vorschlaege aus alten Items.
RESWEEP_MAX_AGE_DAYS = 7

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
    "Sprache: Schweizer Hochdeutsch. Verbindlich: immer 'ss' statt 'ß' und korrekte "
    "Umlaute 'ä'/'ö'/'ü' -- NIEMALS die Umschreibungen 'ae'/'oe'/'ue'. "
    "Schreibe natuerliches, fehlerfreies Deutsch ohne englische Brocken oder erfundene Woerter. "
    "Ton: freundlich, klar und direkt, aber nie forsch oder schroff gegenueber Kunden. "
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

# Echte Outlook-Draft-ID des aktuellen Jobs, deterministisch aus dem
# create_draft-Tool-Ergebnis erfasst. NIEMALS die vom LLM in den JSON-Block
# abgetippte ID verwenden -- lange Graph-IDs (~152 Zeichen) werden vom Modell
# verstuemmelt, was den spaeteren get_email-Abruf (Snapshot/Cleanup/Preview)
# scheitern laesst und die Freigabe-Karte aus dem Cockpit verschwinden laesst.
_job_created_draft_id: str | None = None

# Neue Message-ID, falls die E-Mail im aktuellen Job per move_email_to_folder
# verschoben wurde. Ein Move aendert die Graph-Message-ID (Graph liefert die neue
# ID als ``new_id``). Wird fuer die deterministische Finalisierung benoetigt, damit
# Kategorie/ungelesen auf der FINALEN ID landen und nicht auf einer veralteten.
_job_moved_message_id: str | None = None

# Vollstaendige Menge der im aktuellen Job aufgerufenen Tool-Namen. Bewusst
# UNABHAENGIG vom 200-Event-Trace-Limit gefuehrt: spaete Tools (create_draft,
# search_my_replies, set_categories, update_sender_profile) laufen erst nach
# Schritt 6-7 und fielen sonst aus dem gekappten Trace -- was self_grade und das
# Kontext-Gate systematisch verfaelschte. Quelle der Wahrheit fuer tools_used.
_job_tool_names: set[str] = set()


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

# Triage-Jobtypen: fuer diese greift zusaetzlich der Config-Schalter
# ``triage_disable_thinking`` (Eval-gesteuert, Default aus).
_TRIAGE_JOB_TYPES: set[str] = {"email_triage", "chat_triage"}


def _thinking_disabled(job_type: str | None, skill: str | None) -> bool:
    """True, wenn Thinking fuer diesen Job deaktiviert werden soll (Default: nie).

    Zwei Quellen: die statische Liste ``_THINKING_DISABLED_JOB_TYPES`` (mechanisch)
    und der Config-Schalter ``triage_disable_thinking`` fuer Triage-Jobs. Letzterer
    ist Eval-gesteuert (siehe scripts/eval/ --no-think) und standardmaessig aus,
    weil unsere Triage agentisch mit Tool-Use laeuft.
    """
    if job_type and job_type in _THINKING_DISABLED_JOB_TYPES:
        return True
    if job_type in _TRIAGE_JOB_TYPES and get_settings().triage_disable_thinking:
        return True
    return False


# ── Trace-Callbacks (Transparenz) ────────────────────────

def _trace_append(event: dict) -> None:
    if len(_job_trace) < _MAX_TRACE_EVENTS:
        _job_trace.append(event)


def _on_reasoning(text: str) -> None:
    if text:
        _trace_append({"type": "thinking", "text": str(text)[:2000]})


def _on_tool_start(tc_id, name, args) -> None:
    # Tool-Namen ungekappt mitschreiben (Quelle der Wahrheit fuer tools_used),
    # bevor das 200-Event-Trace-Limit greift.
    if name:
        _job_tool_names.add(str(name))
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


def _extract_draft_id_from_tool_result(result) -> str | None:
    """Liest die echte Draft-ID aus dem (vollstaendigen) create_draft-Tool-Ergebnis.

    Das Tool-Ergebnis ist mehrfach verschachtelt: Hermes wrappt das MCP-Ergebnis als
    ``{"result": "<innerer JSON-String>"}``, und der innere String enthaelt erst das
    eigentliche ``{"id": "<echte Graph-ID>", ...}`` des MCP-Graph-Servers. Wir suchen
    deshalb rekursiv durch Dicts/Listen und JSON-Strings nach dem ersten ``id``-Feld.
    Das Callback erhaelt das ungekuerzte Ergebnis -- so bleibt die lange ID
    (~152 Zeichen) vollstaendig erhalten. Regex auf (auch escaptem) Text als Fallback.
    Gibt ``None`` zurueck, wenn keine ID gefunden wird.
    """

    def _search(obj, depth: int = 0):
        if depth > 6:
            return None
        if isinstance(obj, dict):
            if obj.get("id"):
                return str(obj["id"])
            # Wrapper-Schluessel zuerst (Hermes: "result", MCP-TextContent: "text").
            for key in ("result", "text", "data", "content"):
                if key in obj:
                    found = _search(obj[key], depth + 1)
                    if found:
                        return found
            for value in obj.values():
                found = _search(value, depth + 1)
                if found:
                    return found
            return None
        if isinstance(obj, list):
            for item in obj:
                found = _search(item, depth + 1)
                if found:
                    return found
            return None
        if isinstance(obj, str):
            s = obj.strip()
            if s[:1] in ("{", "["):
                try:
                    return _search(json.loads(s), depth + 1)
                except (json.JSONDecodeError, ValueError):
                    return None
        return None

    if not isinstance(result, str):
        found = _search(result)
        if found:
            return found
        text = str(result)
    else:
        found = _search(result)
        if found:
            return found
        text = result

    # Fallback: toleriere Backslash-escaptes "id":"..." aus doppelt kodiertem JSON.
    m = re.search(r'\\?"id\\?"\s*:\s*\\?"([^"\\]+)', text)
    return m.group(1) if m else None


def _extract_new_id_from_move_result(result) -> str | None:
    """Liest die neue Message-ID aus dem move_email_to_folder-Tool-Ergebnis.

    Der MCP-Graph-Server liefert ``{"status": "moved", ..., "new_id": "<neue ID>"}``,
    von Hermes als ``{"result": "<innerer JSON-String>"}`` gewrappt. Wir suchen
    rekursiv durch Dicts/Listen/JSON-Strings nach dem Feld ``new_id``. Regex als
    Fallback fuer doppelt kodiertes JSON. ``None``, wenn nichts gefunden wird.
    """

    def _search(obj, depth: int = 0):
        if depth > 6:
            return None
        if isinstance(obj, dict):
            if obj.get("new_id"):
                return str(obj["new_id"])
            for key in ("result", "text", "data", "content"):
                if key in obj:
                    found = _search(obj[key], depth + 1)
                    if found:
                        return found
            for value in obj.values():
                found = _search(value, depth + 1)
                if found:
                    return found
            return None
        if isinstance(obj, list):
            for item in obj:
                found = _search(item, depth + 1)
                if found:
                    return found
            return None
        if isinstance(obj, str):
            s = obj.strip()
            if s[:1] in ("{", "["):
                try:
                    return _search(json.loads(s), depth + 1)
                except (json.JSONDecodeError, ValueError):
                    return None
        return None

    found = _search(result)
    if found:
        return found
    text = result if isinstance(result, str) else str(result)
    m = re.search(r'\\?"new_id\\?"\s*:\s*\\?"([^"\\]+)', text)
    return m.group(1) if m else None


def _on_tool_complete(tc_id, name, args, result) -> None:
    global _job_created_draft_id, _job_moved_message_id
    # Tool-Namen vollstaendig (ungekappt) erfassen -- dient als verlaessliche
    # Quelle fuer tools_used/self_grade, unabhaengig vom 200-Event-Trace-Limit.
    if name:
        _job_tool_names.add(str(name))
    # Echte Draft-ID deterministisch aus dem Tool-Ergebnis erfassen (statt aus dem
    # vom LLM abgetippten JSON). Unabhaengig vom 200-Event-Trace-Limit -- so geht
    # die ID auch bei langlaufenden, tool-intensiven Jobs nicht verloren.
    if str(name) == "mcp_graph_create_draft":
        real_id = _extract_draft_id_from_tool_result(result)
        if real_id:
            _job_created_draft_id = real_id  # last-wins: der zuletzt erzeugte Entwurf zaehlt
            logger.info("Echte Draft-ID aus create_draft erfasst (len=%d)", len(real_id))
        else:
            logger.warning(
                "create_draft lief, aber keine ID aus Tool-Ergebnis extrahierbar: %s",
                str(result)[:300],
            )
    # Neue Message-ID nach einem Move deterministisch erfassen -- ein Move aendert
    # die Graph-ID, sodass die spaetere Finalisierung (Kategorie/ungelesen) sonst
    # auf einer veralteten ID landen wuerde. last-wins.
    if str(name) == "mcp_graph_move_email_to_folder":
        new_mid = _extract_new_id_from_move_result(result)
        if new_mid:
            _job_moved_message_id = new_mid
            logger.info("Neue Message-ID nach Move erfasst (len=%d)", len(new_mid))
        else:
            logger.warning(
                "move_email_to_folder lief, aber keine new_id extrahierbar: %s",
                str(result)[:300],
            )
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


# Skill/Kontext, in dem eine Leitregel wirkt. 'general' wirkt immer mit.
_DEFAULT_RULE_CONTEXT = "triage"
# Alte scope-Werte auf die aktiven Kontexte abbilden (Rueckwaertskompatibilitaet).
_SCOPE_CONTEXT_ALIASES: dict[str, str] = {
    "email-triage": "triage",
    "email-style": "draft",
}


async def _build_rules_block(*contexts: str) -> str:
    """Freigegebene LLM-Leitregeln der passenden Kontexte in den Prompt einspeisen.

    Nur ``status='active'`` und ``rule_type='llm'`` wirken; Vorschlaege (``proposed``)
    bleiben bis zur HITL-Freigabe folgenlos, deterministische Regeln laufen separat
    in ``triage.py``. Es greifen Regeln, deren ``scope`` zu einem der ``contexts``
    passt, plus ``general`` (kontextuebergreifend). So wirken Regeln genau dort, wo
    der Kontext aktiv ist -- Triage, Entwurf oder Chat. Best-effort.
    """
    wanted = {_SCOPE_CONTEXT_ALIASES.get(c, c) for c in contexts} or {_DEFAULT_RULE_CONTEXT}
    wanted.add("general")
    try:
        from app.models import LearnedRule

        async with async_session() as db:
            result = await db.execute(
                select(LearnedRule)
                .where(
                    LearnedRule.status == "active",
                    LearnedRule.rule_type == "llm",
                    LearnedRule.scope.in_(tuple(wanted)),
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
        logger.warning("Aktive-Regeln-Block (%s) konnte nicht erzeugt werden", ",".join(sorted(wanted)))
        return ""


async def _build_sender_style_block(from_addr: str) -> str:
    """Per-Absender-Stilprofil in den Prompt einspeisen (Ton-Treffsicherheit).

    Nutzt die ueber Korrekturen gelernten Felder aus ``sender_profiles``
    (Beziehung, Tonalitaet, Sprache, ``learned_tone``, ``style_notes``,
    ``correction_count``). Best-effort -- ohne Profil faellt der Block weg.
    """
    if not from_addr:
        return ""
    try:
        from app.models import SenderProfile

        async with async_session() as db:
            row = await db.execute(
                select(SenderProfile).where(SenderProfile.email == from_addr.lower())
            )
            p = row.scalar_one_or_none()
        if p is None:
            return ""

        facts: list[str] = []
        if p.display_name:
            facts.append(f"Name: {p.display_name}")
        if p.relationship:
            facts.append(f"Beziehung: {p.relationship}")
        if p.tone:
            facts.append(f"Tonalitaet: {p.tone}")
        if p.language:
            facts.append(f"Sprache: {p.language}")

        lines: list[str] = []
        if facts:
            lines.append("- " + "; ".join(facts))
        learned = p.learned_tone if isinstance(p.learned_tone, dict) else {}
        if learned:
            lt = ", ".join(f"{k}={v}" for k, v in learned.items())
            lines.append(f"- Gelernte Tonmerkmale: {lt}")
        notes = (p.style_notes or "").strip()
        if notes:
            # Begrenzen: style_notes ist die einzige unbegrenzte, ueber Korrekturen
            # wachsende Textquelle im Prompt -- Cap haelt den Klassifikations-Prompt
            # schlank (lokale Modelle reagieren empfindlich auf Prompt-Laenge).
            if len(notes) > 600:
                notes = notes[:600].rstrip() + " […]"
            lines.append("- Stil-Notizen aus frueheren Korrekturen:\n" + notes)
        if p.correction_count:
            lines.append(
                f"- Achtung: {p.correction_count} manuelle Stil-Korrektur(en) an diesen "
                "Kontakt erfasst -- richte Anrede, Ton und Laenge besonders genau danach."
            )

        if not lines:
            return ""
        return (
            "\n---\n\n## ABSENDER-STILPROFIL (fuer diesen Kontakt -- VERBINDLICH beim Draft)\n"
            "Beachte das gelernte Profil dieses Absenders genau (Anrede/Du-Sie, Ton, Laenge):\n"
            + "\n".join(lines) + "\n"
        )
    except Exception:  # noqa: BLE001 - best-effort
        logger.warning("Sender-Style-Block konnte nicht erzeugt werden")
        return ""


async def _build_project_routing_hint(from_addr: str) -> str:
    """Gelerntes Projekt-Routing als weichen Prompt-Hinweis ("korrekte Zuweisung").

    Wertet die impliziten Korrektursignale (``task_moved``) dieses Absenders aus:
    Wenn agent-erzeugte Tasks dieses Kontakts wiederholt ins selbe Projekt
    verschoben wurden, bevorzugt der Agent kuenftig dieses Projekt fuer
    ``suggested_project``. Bewusst nicht-destruktiv -- die Task bleibt
    ``needs_review``, der Agent darf inhaltlich abweichen. Best-effort: ohne
    genuegend Signale (Schwelle: ``agent_reflection_min_occurrences``) faellt der
    Block ersatzlos weg.
    """
    if not from_addr:
        return ""
    try:
        import uuid as _uuid
        from collections import Counter as _Counter

        threshold = max(2, get_settings().agent_reflection_min_occurrences)
        async with async_session() as db:
            rows = await db.execute(
                select(AgentFeedback.corrected).where(
                    AgentFeedback.feedback_type == "task_moved",
                    func.lower(AgentFeedback.sender_email) == from_addr.lower(),
                )
            )
            targets: _Counter = _Counter()
            for (corrected,) in rows.all():
                pid = (corrected or {}).get("project_id")
                if pid:
                    targets[str(pid)] += 1
            if not targets:
                return ""
            top_pid, top_count = targets.most_common(1)[0]
            if top_count < threshold:
                return ""
            try:
                proj = await db.get(Project, _uuid.UUID(top_pid))
            except (ValueError, TypeError):
                return ""
        if proj is None or getattr(proj, "status", None) == "archived":
            return ""
        return (
            "\n---\n\n## GELERNTES PROJEKT-ROUTING (weicher Hinweis)\n"
            f"Aufgaben von {from_addr} hat der Berater bereits {top_count}x ins "
            f'Projekt "{proj.name}" verschoben. Bevorzuge dieses Projekt fuer '
            "suggested_project, sofern der Inhalt nicht klar zu einem anderen "
            "Projekt gehoert.\n"
        )
    except Exception:  # noqa: BLE001 - best-effort, darf den Prompt-Bau nie stoppen
        logger.warning("Projekt-Routing-Hinweis konnte nicht erzeugt werden")
        return ""


async def _build_thread_task_hint(meta: dict) -> str:
    """Weicher Thread-/Konsistenz-Hinweis: existiert bereits ein offener Task zur
    selben Sache (gleicher Thread oder Absender+Betreff), wird der Agent darauf
    hingewiesen, KEINEN doppelten Task zu erzeugen. Die harte Garantie liegt
    weiterhin in der Dedup-Logik des Post-Processings (``_find_duplicate_open_task``);
    dieser Hinweis reduziert das Rauschen bereits im Prompt und haelt die
    Klassifikation ueber einen Thread hinweg konsistent. Best-effort.
    """
    try:
        async with async_session() as db:
            dup = await _find_duplicate_open_task(db, meta)
            if dup is None:
                return ""
            proj = await db.get(Project, dup.project_id) if dup.project_id else None
        proj_txt = f' (Projekt "{proj.name}")' if proj is not None else ""
        return (
            "\n---\n\n## BEREITS OFFENER TASK ZU DIESER SACHE (KONSISTENZ)\n"
            f'Es existiert bereits ein offener Task: "{dup.title}"{proj_txt}. '
            "Erstelle KEINEN doppelten Task. Handelt es sich um dieselbe Sache, "
            "genuegt fyi -- das Backend dockt die neue Meldung automatisch als "
            "Checklisten-Eintrag an den bestehenden Task an.\n"
        )
    except Exception:  # noqa: BLE001 - best-effort
        logger.warning("Thread-Task-Hinweis konnte nicht erzeugt werden")
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
    two_pass = get_settings().two_pass_draft
    # Im Zwei-Pass-Modus schreibt ein separater Lauf den Entwurf -> hier nur der
    # Triage-Regel-Kontext. Im Einpass-Modus laufen Triage + Draft zusammen.
    rules_block = await _build_rules_block("triage") if two_pass else await _build_rules_block("triage", "draft")
    sender_style_block = await _build_sender_style_block(from_addr)
    routing_hint = await _build_project_routing_hint(from_addr)
    thread_task_hint = await _build_thread_task_hint(meta)

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
    # Im Zwei-Pass-Modus entfaellt sie hier -- der separate Schreib-Pass laedt den
    # Stil-Kanon mit vollem Budget; die Klassifikation bleibt schlank.
    if two_pass:
        style_section = ""
    elif style_native:
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

    # Draft-Schritt: im Zwei-Pass-Modus erstellt der Klassifikations-Lauf KEINEN
    # Entwurf (das uebernimmt der separate Schreib-Pass), sonst im selben Loop.
    if two_pass:
        draft_step = (
            "7. Erstelle KEINEN Antwort-Entwurf. Klassifiziere nur -- bei auto_reply "
            "schreibt das Backend den Entwurf anschliessend in einem separaten, "
            "fokussierten Schreib-Pass. Das Backend erzwingt die Thread-Zugehörigkeit "
            "und erstellt bei task die Aufgabe automatisch."
        )
    else:
        draft_step = (
            "7. Erstelle Draft falls auto_reply. WICHTIG: Rufe VORHER "
            f'search_my_replies("{from_addr}") auf und nutze die letzten von Anthony '
            "gesendeten Antworten an diesen Kontakt als Ton-/Register-Kalibrierung "
            "(orientiere dich an Ton, Länge, Anrede und Schlussformel, schreibe aber "
            "natürlich neu, kopiere nicht wörtlich). PFLICHT: Übergib bei create_draft "
            f'IMMER reply_to_id="{email_id}", damit die Antwort als "Allen antworten" '
            "im selben Thread landet (NIEMALS einen neuen Thread starten). Empfänger "
            "NICHT manuell überschreiben — die Antwort übernimmt die korrekten "
            "Empfänger (To + CC der Diskussion) automatisch. (Hinweis: Das Backend "
            "erzwingt die Thread-Zugehörigkeit ohnehin deterministisch; ein neuer "
            "Thread wird automatisch korrigiert. Bei task übernimmt das Backend die "
            "Task-Erstellung automatisch.)"
        )

    return f"""{correction_block}{skill_section}

---

{projects_context}
{routing_hint}{thread_task_hint}{recall_block}{rules_block}
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
{style_section}{sender_style_block}
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
{draft_step}
8. Gib den PFLICHT-JSON-Block aus (Schema im Skill bzw. references/triage-rules.md)
9. Aktualisiere das Absender-Profil mit update_sender_profile (siehe Skill)

Status und Output werden automatisch aus deiner finalen Antwort gespeichert -- rufe update_agent_job NICHT selbst auf.
""" + (f"\n\n## ZUSÄTZLICHE BENUTZER-REGELN (haben Vorrang!)\n{custom_triage_prompt}" if custom_triage_prompt else "")


async def _build_draft_prompt(meta: dict) -> str:
    """Baut den fokussierten Schreib-Prompt fuer den Zwei-Pass-Draft.

    Einzige Aufgabe: den besten Antwort-Entwurf in Anthonys Stimme schreiben --
    getrennt von der Klassifikation, ohne JSON-/Move-/Task-Druck. Der Lauf laedt
    den Stil-Kanon, den Thread und die letzten eigenen Antworten (Kalibrierung) und
    erstellt den Entwurf mit erzwungenem ``reply_to_id`` im selben Thread.
    """
    email_id = meta.get("email_message_id", "")
    from_addr = meta.get("from_address", "")
    from_name = meta.get("from_name", "")
    subject = meta.get("subject", "")
    conversation_id = meta.get("conversation_id", "")
    preview = (meta.get("body_preview") or "")[:300]

    style_native = _style_skill_available()
    if style_native:
        style_section = (
            "## SCHREIBSTIL (ZUERST laden und strikt befolgen)\n"
            "→ **skill_view(name='email-style')** -- natürliche Stimme, Anrede-/"
            "Register-Spiegelung, Tonalitätsstufen, Self-Review.\n"
        )
    else:
        style_text = _load_style_profile()
        style_section = (
            "## SCHREIBSTIL (VERBINDLICH)\n\n"
            f"{style_text}\n" if style_text else ""
        )
    sender_style_block = await _build_sender_style_block(from_addr)
    rules_block = await _build_rules_block("draft")

    thread_load = (
        f'→ **get_thread("{conversation_id}")** -- vollständiger Thread-Kontext.\n'
        if conversation_id else ""
    )

    return f"""{style_section}{sender_style_block}{rules_block}
---

## AUFGABE: ANTWORT-ENTWURF SCHREIBEN

Diese E-Mail wurde als **auto_reply** eingestuft. Schreibe jetzt den bestmöglichen
Antwort-Entwurf im persönlichen Stil von Anthony Smith. Klassifiziere NICHT neu,
verschiebe nichts, erstelle keinen Task -- schreibe nur den Entwurf.

**E-Mail Message-ID:** {email_id}
**Betreff:** {subject}
**Von:** {from_name} <{from_addr}>
**Vorschau:** {preview}

### Vorgehen
1. **get_email("{email_id}")** -- lies die vollständige E-Mail (nicht nur die Vorschau).
{thread_load}2. **search_my_replies("{from_addr}")** -- nimm die letzten eigenen Antworten an
   diesen Kontakt als Ton-/Register-Kalibrierung (Anrede, Länge, Schlussformel).
   Orientiere dich daran, **kopiere aber nicht wörtlich** -- schreibe passend zum
   aktuellen Inhalt neu.
3. **Spiegle das Register** des Absenders (Du/Sie und Grussform, siehe Schreibstil).
   Schreibt er «Hallo Anthony», antworte «Hallo [Vorname]», nicht «Lieber/Liebe».
4. Formuliere natürlich und flüssig, halte dich an den Self-Review im email-style-Skill.
5. **create_draft** mit **reply_to_id="{email_id}"** (Antwort im selben Thread,
   NIE ein neuer Thread). Empfänger NICHT manuell überschreiben -- To + CC der
   Diskussion werden automatisch übernommen. Das Backend erzwingt die Thread-
   Zugehörigkeit ohnehin deterministisch.

Gib nach dem create_draft-Aufruf eine kurze Bestätigung aus (kein JSON nötig).
"""


async def _build_chat_triage_prompt(job: AgentJob) -> str:
    """Baut den Prompt für einen chat_triage Job mit Kontext."""
    meta = job.metadata_json or {}
    chat_id = meta.get("chat_id", "")
    message_id = meta.get("chat_message_id", "")
    sender = meta.get("from_name", "")
    preview = meta.get("body_preview", "")

    projects_context = await _load_projects_context()
    rules_block = await _build_rules_block("triage", "chat")

    return f"""## CHAT-TRIAGE JOB

Du hast eine neue Microsoft Teams Chat-Nachricht erhalten. Analysiere und klassifiziere sie.
Sprache: Schweizer Hochdeutsch (ss statt scharfem S, korrekte Umlaute ä/ö/ü).

{projects_context}
{rules_block}
**Job-ID:** {job.id}
**Chat-ID:** {chat_id}
**Nachricht-ID:** {message_id}
**Absender:** {sender}
**Vorschau:** {preview[:300]}

## VORGEHEN

1. Lies die vollständige Nachricht mit den verfügbaren MCP-Tools.
2. Klassifiziere zurückhaltend (fail-closed): `task` nur, wenn klar eine konkrete
   Handlung von Anthony nötig ist. Reine Infos, Bestätigungen, Small Talk -> `fyi`.
3. Bei `task`: Erstelle einen TaskPilot-Task mit Kontext-Briefing und passendem Projekt.
4. Bei `fyi`: Nur zur Kenntnis nehmen.

## PFLICHT: JSON-Block am Ende

Gib als Letztes einen JSON-Block aus (ohne ihn kann das Backend die Einordnung nicht speichern):

```json
{{"triage_class": "task|fyi", "confidence": 0.0, "rationale": "kurze Begründung"}}
```

Status und Output werden automatisch aus deiner finalen Antwort gespeichert -- rufe update_agent_job NICHT selbst auf.
"""


async def _post_process_chat_triage(job_id, content: str) -> str:
    """Schreibt die Chat-Klassifikation nach dem LLM-Lauf in ``chat_triage`` zurueck.

    Analog zur E-Mail-Triage: ohne diesen Schritt blieb ``chat_triage.triage_class``
    dauerhaft NULL (Jobs wurden zwar abgeschlossen, aber die Einordnung nie
    persistiert). Fail-closed: ohne verwertbaren JSON-Block wird ``fyi`` gesetzt.
    """
    parsed = _extract_json_block(content)
    triage_class = None
    rationale = None
    confidence = None
    if parsed is not None:
        triage_class = parsed.get("triage_class")
        if triage_class == "quick_response":
            triage_class = "auto_reply"
        rationale = parsed.get("rationale")
        confidence = parsed.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
            if confidence is not None:
                if confidence > 1:
                    confidence = confidence / 100.0
                confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = None

    if triage_class not in ("task", "fyi", "auto_reply"):
        triage_class = "fyi"

    async with async_session() as db:
        await db.execute(
            update(ChatTriage)
            .where(ChatTriage.agent_job_id == job_id)
            .values(
                triage_class=triage_class,
                confidence=confidence,
                suggested_action={
                    "triage_class": triage_class,
                    "rationale": rationale,
                    "confidence": confidence,
                    "fallback": parsed is None,
                },
                status="acted",
            )
        )
        await db.commit()
    logger.info("Job %s: Chat-Triage -> %s (confidence=%s)", job_id, triage_class, confidence)
    return "completed"


def _format_task_context(task: Task) -> str:
    """Baut den vollständigen Auftragskontext einer Task für den Agenten.

    Nutzt ausschliesslich bestehende Task-Relationen (Titel, Beschreibung,
    Checkliste, Anhänge, Tags, externe Referenzen) -- keine neuen Attribute.
    Leere Bereiche werden weggelassen, damit der Prompt nicht verrauscht.
    """
    parts: list[str] = [f"**{task.title}**"]
    if task.description:
        parts.append(task.description)

    # Checkliste als konkrete Teilschritte (offen vs. erledigt, in Reihenfolge)
    items = sorted(task.checklist_items or [], key=lambda c: c.position)
    if items:
        offen = sum(1 for c in items if not c.is_checked)
        lines = [f"- [{'x' if c.is_checked else ' '}] {c.text}" for c in items]
        parts.append(
            f"### Checkliste ({offen} offen / {len(items)} total)\n" + "\n".join(lines)
        )

    # Anhänge: Dateinamen + Hinweis. Die extrahierten Textinhalte werden vom
    # Aufrufer (_build_generic_prompt) separat als 'Anhang-Inhalte' eingebettet.
    attachments = task.attachments or []
    if attachments:
        lines = [
            f"- {a.filename} ({a.mime_type or 'unbekannt'}) → {a.filepath}"
            for a in attachments
        ]
        parts.append(
            "### Anhänge\n"
            "Die extrahierten Textinhalte der Anhänge stehen unten unter "
            "'Anhang-Inhalte'. Bilder analysierst du bei Bedarf mit vision_analyze, "
            "OneDrive-Dateien (onedrive://) lädst du bei Bedarf mit download_file "
            "nach:\n" + "\n".join(lines)
        )

    # Tags als Themen-/Kategorie-Hinweis
    tags = task.tags or []
    if tags:
        parts.append("**Tags:** " + ", ".join(t.name for t in tags))

    # Externe Referenzen: gezielt per MCP nachladbar
    refs: list[str] = []
    if task.email_message_id:
        refs.append(f"E-Mail message_id={task.email_message_id} (Graph-MCP)")
    if task.email_conversation_id:
        refs.append(f"E-Mail conversation_id={task.email_conversation_id} (Graph-MCP)")
    if task.calendar_event_id:
        refs.append(f"Kalender event_id={task.calendar_event_id} (Graph-MCP)")
    if task.pipedrive_deal_id:
        refs.append(f"Pipedrive deal_id={task.pipedrive_deal_id} (Pipedrive-MCP)")
    if task.pipedrive_person_id:
        refs.append(f"Pipedrive person_id={task.pipedrive_person_id} (Pipedrive-MCP)")
    if refs:
        parts.append(
            "### Verknüpfte Referenzen\n"
            "Lade den Kontext bei Bedarf gezielt per MCP nach:\n"
            + "\n".join(f"- {r}" for r in refs)
        )

    return "\n\n".join(parts)


async def _resolve_task_attachment_context(task: Task) -> str:
    """Extrahiert die Inhalte der Task-Anhänge als `<attached_files>`-Block.

    Lokale Uploads (Pfad unter `/uploads/...`) und OneDrive-Referenzen
    (`onedrive://{item_id}`) werden via `context_resolver` aufgelöst, damit der
    Agent die Dokumentinhalte direkt im Prompt vorfindet statt nur Metadaten.
    Bilder/nicht-Text-Formate werden vom Resolver entsprechend markiert.
    """
    attachments = task.attachments or []
    if not attachments:
        return ""

    sources: list[dict] = []
    for a in attachments:
        path = a.filepath or ""
        if path.startswith("onedrive://"):
            sources.append({
                "type": "onedrive_file",
                "item_id": path[len("onedrive://"):],
                "name": a.filename,
            })
        elif path.startswith("/uploads/"):
            sources.append({
                "type": "local_upload",
                "upload_id": path[len("/uploads/"):],
                "name": a.filename,
            })

    if not sources:
        return ""

    from app.services.context_resolver import resolve_context_sources

    graph_client = None
    if any(s["type"].startswith("onedrive") for s in sources):
        from app.services.graph import get_graph_client

        graph_client = get_graph_client()

    try:
        ctx = await resolve_context_sources(sources, graph_client)
        return ctx.to_llm_context()
    except Exception:  # noqa: BLE001 - best-effort, darf den Job nie blockieren
        logger.exception("Auflösung der Task-Anhänge fehlgeschlagen")
        return ""


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

    description = meta.get("description") or meta.get("prompt")
    # Tasks, die im Cockpit/Board dem Agenten zugewiesen werden, tragen den Auftrag
    # in Titel + Beschreibung der verknüpften Task (nicht in metadata_json). Ohne das
    # Nachladen bekäme der Agent einen leeren Auftrag ("nichts zu tun"). Wir laden den
    # gesamten vorhandenen Task-Kontext (Checkliste, Anhänge, Tags, Referenzen) nach.
    if not description and job.task_id:
        async with async_session() as db:
            task = (
                await db.execute(
                    select(Task)
                    .options(
                        selectinload(Task.checklist_items),
                        selectinload(Task.attachments),
                        selectinload(Task.tags),
                    )
                    .where(Task.id == job.task_id)
                )
            ).scalar_one_or_none()
        if task:
            description = _format_task_context(task)
            attached = await _resolve_task_attachment_context(task)
            if attached:
                description += "\n\n### Anhang-Inhalte\n\n" + attached
    if not description:
        description = str(meta)

    # Leitregeln je nach Job-Typ: Chat-Agent -> 'chat', E-Mail-Versand -> 'draft'.
    # Andere generische Jobs erhalten nur die kontextuebergreifenden 'general'-Regeln.
    _rule_contexts = {
        "chat_agent": ("chat",),
        "send_email": ("draft",),
    }.get(job.job_type or "", ())
    rules_block = await _build_rules_block(*_rule_contexts)

    return f"""## AGENT-JOB

{projects_context}
{skill_hint}{style_hint}{rules_block}

**Job-ID:** {job.id}
**Job-Typ:** {job.job_type or 'generic'}
**Auftrag:** {description}

Führe den Auftrag aus und gib dein **vollständiges** Ergebnis direkt als finale Antwort aus -- formatiert als Markdown (Überschriften, Listen, Fettungen, wo sinnvoll). Deine Antwort selbst ist das gespeicherte Resultat; es gibt keinen separaten Speicherort und keine "Kurzfassung". Rufe update_agent_job NICHT selbst auf -- Status und Output werden automatisch aus deiner finalen Antwort gespeichert.
"""


# ── Post-Processing (framework-agnostisch) ───────────────

def _loads_lenient(raw: str) -> dict | None:
    """Parst einen JSON-Objekt-String tolerant.

    Lokale Modelle liefern den Pflicht-Block oft leicht abweichend: Code-Fence-
    Reste, trailing commas oder Python-Stil mit einfachen Anfuehrungszeichen.
    Diese Funktion versucht der Reihe nach: striktes JSON, JSON ohne trailing
    commas, und als letzter Ausweg ``ast.literal_eval`` (Python-Dict-Literal).
    Gibt nur dict zurueck (sonst None).
    """
    if not raw:
        return None
    s = raw.strip().strip("`").strip()
    # 1) Striktes JSON (deckt true/false/null korrekt ab).
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass
    # 2) Trailing commas vor schliessender Klammer entfernen.
    try:
        obj = json.loads(re.sub(r",(\s*[}\]])", r"\1", s))
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass
    # 3) Python-Dict-Literal (einfache Quotes). literal_eval kennt kein
    #    true/false/null -> nur als letzter Ausweg, daher zuvor mappen.
    try:
        py = re.sub(r"\btrue\b", "True", s)
        py = re.sub(r"\bfalse\b", "False", py)
        py = re.sub(r"\bnull\b", "None", py)
        obj = ast.literal_eval(py)
        if isinstance(obj, dict):
            return obj
    except (ValueError, SyntaxError, TypeError):
        pass
    return None


def _iter_balanced_objects(text: str):
    """Liefert alle klammer-balancierten ``{...}``-Teilstrings (String-/Escape-sicher).

    Im Gegensatz zu einer flachen Regex erfasst dies auch Objekte mit
    verschachtelten Feldern (z. B. ``categories``-Arrays oder Sub-Objekte).
    """
    depth = 0
    start = -1
    in_str = False
    escape = False
    quote = ""
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    yield text[start : i + 1]
                    start = -1


def _extract_json_block(content: str) -> dict | None:
    """Extrahiert den Triage-JSON-Block robust aus dem LLM-Output.

    Lokale Modelle formatieren den Pflicht-Block inkonsistent: Fence fehlt,
    Felder sind verschachtelt, die Reihenfolge weicht ab oder es steht Prosa
    drumherum. Frueher griff nur eine sehr enge Regex (Fence ODER flaches
    ``{...}`` mit ``label`` UND ``triage_class`` ohne Verschachtelung) -- ~11%
    der Jobs fielen deshalb still durch (keine Klasse persistiert).

    Diese Implementierung scannt alle klammer-balancierten Objekte, parst sie
    tolerant und waehlt das **letzte** valide Objekt mit ``triage_class`` (der
    Abschluss-Block steht in der Regel am Ende der Antwort). Gibt None zurueck,
    wenn nichts Verwertbares vorhanden ist -- der Aufrufer eskaliert dann
    (Retry/Fallback), statt still zu verwerfen.
    """
    if not content:
        return None

    candidates: list[dict] = []
    for raw in _iter_balanced_objects(content):
        obj = _loads_lenient(raw)
        if isinstance(obj, dict):
            candidates.append(obj)

    if not candidates:
        return None

    for obj in reversed(candidates):
        if "triage_class" in obj:
            return obj
    # Kein Objekt mit triage_class -> bestmoegliches letztes Objekt (Best-Effort).
    return candidates[-1]


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


async def _finalize_email_state(
    meta: dict,
    label: str | None,
    moved_id: str | None,
) -> None:
    """Deterministische Finalisierung des Outlook-Zustands nach der Triage.

    Zwei Garantien, die NICHT dem (unzuverlaessigen) LLM ueberlassen werden:

    1. Kategorie-Sicherheitsnetz: Hat die Mail nach der Triage noch GAR KEINE
       Outlook-Kategorie, wird sie aus dem JSON-``label`` nachgezogen. Eine vom
       Agenten bereits gesetzte Kategorie wird NIE ueberschrieben.
    2. ``mark_as_unread`` als ALLERLETZTER Graph-Schritt -- immer. Ein
       ``set_categories``-PATCH kippt ``isRead`` in Exchange auf ``true``; nur wenn
       das ungelesen-Setzen zuletzt laeuft, bleibt die Mail fuer Anthony sichtbar
       neu.

    Laeuft auf der FINALEN Message-ID: ``moved_id`` (nach einem Move) hat Vorrang
    vor ``email_message_id``. Best-effort und 404-tolerant (CC-only-Mails / bereits
    veraltete IDs duerfen den Job nicht stoppen), andere Fehler werden geloggt.
    """
    final_mid = moved_id or meta.get("email_message_id")
    if not final_mid:
        return

    client = await _build_graph_client()
    if client is None:
        return
    try:
        # Schritt 1: Kategorie nur als Luecken-Fueller (Agent-Arbeit nie ueberschreiben).
        if label and label != "Unklassifiziert":
            try:
                existing = await client.get_email_categories(final_mid)
                if not (existing or {}).get("categories"):
                    await client.set_categories(final_mid, [label])
                    logger.info("Finalize: Kategorie '%s' nachgezogen (Sicherheitsnetz)", label)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status == 404:
                    logger.info("Finalize: Kategorie nicht setzbar (404, z. B. CC-only/veraltete ID)")
                else:
                    logger.warning("Finalize: Kategorie-Schritt fehlgeschlagen (HTTP %s)", status)

        # Schritt 2: IMMER und als letzte Aktion -- Mail auf ungelesen zuruecksetzen.
        try:
            await client.mark_as_unread(final_mid)
            logger.info("Finalize: Mail auf ungelesen gesetzt (mid=%s)", str(final_mid)[:40])
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 404:
                logger.info("Finalize: ungelesen nicht setzbar (404, z. B. CC-only/veraltete ID)")
            else:
                logger.warning("Finalize: ungelesen-Schritt fehlgeschlagen (HTTP %s)", status)
    except Exception:  # noqa: BLE001 - Finalisierung darf den Job nie stoppen
        logger.warning("Finalize: unerwarteter Fehler (mid=%s)", str(final_mid)[:40])
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001
            pass


def _normalize_conversation_id(value: str | None) -> str:
    """conversationId fuer den Vergleich normalisieren (None/Leerstring -> '')."""
    return (value or "").strip()


async def _ensure_draft_in_thread(
    draft_id: str,
    email_message_id: str,
    snapshot: dict | None,
) -> tuple[str, dict | None]:
    """Garantiert deterministisch, dass der Entwurf im Original-Thread liegt.

    Der Agent SOLL bei ``create_draft`` ``reply_to_id`` setzen, damit die Antwort
    via ``createReplyAll`` im selben Thread (gleiche ``conversationId``) landet und
    die korrekten Empfaenger uebernimmt. Verlaesst sich aber das LLM nicht darauf,
    entsteht ein NEUER Thread (``POST /messages``) -- Anthony und die Empfaenger
    sehen die urspruengliche Diskussion dann nicht.

    Diese Funktion prueft die ``conversationId`` des Entwurfs gegen den Original-
    Thread (ground truth via ``get_email``) und repariert bei Abweichung: Der
    Agent-Body wird in einen korrekten Reply-All-Entwurf uebernommen, der falsche
    Entwurf geloescht. Gibt ``(draft_id, snapshot)`` zurueck -- bei Reparatur die
    neuen Werte. Best-effort: Fehler duerfen den Job nicht stoppen.
    """
    if not (draft_id and email_message_id and snapshot):
        return draft_id, snapshot

    client = await _build_graph_client()
    if client is None:
        return draft_id, snapshot
    try:
        original = await client.get_email(email_message_id)
        original_conv = _normalize_conversation_id(original.get("conversationId"))
        draft_conv = _normalize_conversation_id(snapshot.get("conversation_id"))

        # Original-conversationId unbekannt -> keine verlaessliche Aussage moeglich.
        if not original_conv:
            logger.warning(
                "Thread-Check: Original-conversationId fehlt (email_message_id=%s), "
                "ueberspringe Reparatur",
                str(email_message_id)[:40],
            )
            return draft_id, snapshot

        if draft_conv == original_conv:
            return draft_id, snapshot

        # Abweichung -> Agent hat einen neuen/falschen Thread erzeugt. Reparieren.
        logger.warning(
            "Thread-Check: Entwurf liegt im falschen Thread (draft_conv=%s != "
            "original_conv=%s), erstelle Reply-All im Original-Thread neu",
            draft_conv or "<leer>", original_conv,
        )
        body_html = snapshot.get("body_html") or ""
        subject = original.get("subject") or ""
        from_addr = (
            original.get("from", {}).get("emailAddress", {}).get("address")
            or original.get("sender", {}).get("emailAddress", {}).get("address")
            or ""
        )
        fixed = await client.create_draft(
            subject=subject,
            body_html=body_html,
            to_recipients=[from_addr] if from_addr else [],
            reply_to_id=email_message_id,
            reply_all=True,
        )
        new_draft_id = fixed.get("id")
        if not new_draft_id:
            logger.warning("Thread-Reparatur fehlgeschlagen: kein neue draft_id erhalten")
            return draft_id, snapshot

        # Falschen Entwurf entfernen (best-effort).
        try:
            await client.delete_message(draft_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Thread-Reparatur: falschen Entwurf konnte nicht geloescht werden "
                "(draft_id=%s)", str(draft_id)[:40],
            )

        new_snapshot = await _snapshot_agent_draft(new_draft_id)
        logger.info(
            "Thread-Reparatur erfolgreich: neue draft_id=%s im Original-Thread",
            str(new_draft_id)[:40],
        )
        return new_draft_id, (new_snapshot or snapshot)
    except Exception:  # noqa: BLE001 - darf den Job nie stoppen
        logger.warning(
            "Thread-Check fehlgeschlagen (draft_id=%s)", str(draft_id)[:40]
        )
        return draft_id, snapshot
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001
            pass


def _json_retry_prompt(prev: str) -> str:
    """Strikter Nachfass-Prompt: erzwingt NUR den Pflicht-JSON-Block.

    Wird genau einmal ausgefuehrt, wenn der erste Lauf keinen verwertbaren Block
    lieferte. Leitet die Werte aus der bereits erstellten Analyse ab, ohne erneut
    Tools zu bemuehen.
    """
    tail = (prev or "")[-4000:]
    return (
        "Deine vorherige Antwort enthielt keinen maschinenlesbaren Pflicht-JSON-Block. "
        "Gib jetzt AUSSCHLIESSLICH den JSON-Block aus -- kein Text davor oder danach, "
        "keine weiteren Tool-Aufrufe -- in einem ```json ... ``` Codeblock.\n"
        "Pflichtfelder: triage_class (genau einer von \"auto_reply\", \"task\", \"fyi\"), "
        "label, reply_expected (true/false), confidence (Zahl 0..1), rationale. "
        "Bei task zusaetzlich: task_title, task_description, suggested_project, deadline.\n\n"
        "Leite die Werte aus deiner bisherigen Analyse ab:\n---\n" + tail + "\n---\n"
    )


_INTERNAL_NOISE_RE = re.compile(
    r"(?:\b404\b|\b400\b|HTTPStatusError|Bad Request|Not Found|createReply(?:All)?|"
    r"per Graph[- ]?API|via Graph[- ]?API|Graph[- ]?API nicht|"
    r"l(?:ä|ae)sst sich (?:nicht|per|via)|liess sich (?:nicht|per|via))",
    re.IGNORECASE,
)


def _strip_internal_notes(text: str | None) -> str | None:
    """Entfernt interne API-/Fehler-Diagnosen aus nutzersichtbarem Text.

    Der Agent schreibt gelegentlich technische Hinweise (404, HTTPStatusError,
    createReplyAll, "via Graph API nicht lesbar") in task_description/Rationale.
    Solche Saetze lesen sich im Cockpit wie ein Fehlschlag ("ging nicht") und
    gehoeren nicht in die nutzersichtbare Aufgabe -- sie werden satzweise entfernt.
    """
    if not text:
        return text
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    kept = [p for p in parts if p.strip() and not _INTERNAL_NOISE_RE.search(p)]
    cleaned = " ".join(s.strip() for s in kept).strip()
    return cleaned or None


def _outlook_deeplink(message_id: str | None) -> str | None:
    """Baut einen Outlook-Web-Deeplink auf eine E-Mail aus ihrer Graph-Message-ID."""
    if not message_id:
        return None
    return f"https://outlook.office.com/mail/deeplink/read/{quote(message_id, safe='')}"


def _email_reference_block(meta: dict) -> str:
    """Strukturierter Quell-E-Mail-Block (Von/Betreff/Deeplink) fuer Task-Beschreibungen."""
    lines: list[str] = []
    from_name = (meta.get("from_name") or "").strip()
    from_addr = (meta.get("from_address") or "").strip()
    subject = (meta.get("subject") or "").strip()
    if from_addr or from_name:
        lines.append(f"Von: {from_name} <{from_addr}>".strip())
    if subject:
        lines.append(f"Betreff: {subject}")
    deeplink = _outlook_deeplink(meta.get("email_message_id"))
    if deeplink:
        lines.append(f"E-Mail oeffnen: {deeplink}")
    if not lines:
        return ""
    return "\n\n---\nQuell-E-Mail:\n" + "\n".join(lines)


_SUBJECT_PREFIX_RE = re.compile(r"^(?:\s*(?:re|aw|fw|wg|fwd|antw| w)\s*:\s*)+", re.IGNORECASE)


def _normalize_subject(subject: str | None) -> str:
    """Normalisiert einen Betreff fuer den Duplikat-Vergleich.

    Entfernt wiederholte Antwort-/Weiterleitungs-Praefixe (RE:/AW:/FW:/WG: ...)
    und kollabiert Whitespace -- damit praktisch identische Betreffzeilen
    (z. B. wiederkehrende Fehler-Mails) als gleich erkannt werden.
    """
    s = subject or ""
    prev = None
    while prev != s:
        prev = s
        s = _SUBJECT_PREFIX_RE.sub("", s.strip())
    return re.sub(r"\s+", " ", s).strip().lower()


async def _find_duplicate_open_task(db, meta: dict) -> Task | None:
    """Sucht einen bereits offenen Task zur selben Sache (Konversation oder Absender+Betreff).

    Verhindert, dass aus vielen praktisch identischen E-Mails (z. B. wiederkehrende
    System-Fehlermeldungen) immer wieder neue, redundante Tasks entstehen. Gibt den
    aeltesten passenden **offenen** (nicht erledigten) Task zurueck oder ``None``.
    """
    conv = meta.get("conversation_id")
    from_addr = (meta.get("from_address") or "").strip().lower()
    norm_subject = _normalize_subject(meta.get("subject"))

    # Schneller Pfad: gleicher Thread hat bereits einen offenen Task.
    if conv:
        res = await db.execute(
            select(Task)
            .where(Task.email_conversation_id == conv, Task.is_completed.is_(False))
            .order_by(Task.created_at)
            .limit(1)
        )
        dup = res.scalar_one_or_none()
        if dup is not None:
            return dup

    # Absender + normalisierter Betreff: faengt wiederkehrende, praktisch
    # identische Mails, die je eine eigene Konversation haben (z. B. n8n-Alerts).
    if from_addr and norm_subject:
        res = await db.execute(
            select(Task, EmailTriage.subject)
            .join(EmailTriage, EmailTriage.message_id == Task.email_message_id)
            .where(
                Task.is_completed.is_(False),
                Task.email_message_id.isnot(None),
                func.lower(EmailTriage.from_address) == from_addr,
            )
            .order_by(Task.created_at)
            .limit(100)
        )
        for task, subj in res.all():
            if _normalize_subject(subj) == norm_subject:
                return task
    return None


async def _append_duplicate_note(db, task: Task, meta: dict) -> None:
    """Dockt eine weitere Meldung als Checklisten-Eintrag an einen offenen Task an."""
    subj = meta.get("subject") or "(kein Betreff)"
    when = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    pos_res = await db.execute(
        select(ChecklistItem.position)
        .where(ChecklistItem.task_id == task.id)
        .order_by(ChecklistItem.position.desc())
        .limit(1)
    )
    next_pos = (pos_res.scalar_one_or_none() or 0) + 1
    db.add(
        ChecklistItem(
            task_id=task.id,
            text=f"Weitere Meldung am {when}: {subj}"[:500],
            is_checked=False,
            position=next_pos,
        )
    )
    task.updated_at = datetime.now(timezone.utc)
    await db.flush()


async def _create_email_task(
    db,
    job_id,
    meta: dict,
    *,
    task_title: str,
    task_description: str | None,
    suggested_project: str | None,
    deadline: str | None,
    reply_expected: bool = False,
) -> Task | None:
    """Legt aus einer triagierten E-Mail eine Task an (geteilt von Normal- + Fallback-Pfad).

    Waehlt das passende Projekt (oder das erste), die erste Board-Spalte und die
    Pipeline-Spalte nach Deadline. Verknuepft ``email_message_id`` /
    ``email_conversation_id`` und setzt ``needs_review=True``. Gibt die Task
    zurueck oder None, wenn kein Projekt/keine Spalte existiert.

    Duplikat-Schutz: Existiert bereits ein offener Task zur selben Sache (gleiche
    Konversation oder Absender+Betreff), wird KEIN neuer Task erstellt. Stattdessen
    wird die neue Meldung als Checklisten-Eintrag angedockt und die zugehoerige
    ``email_triage`` als dedupliziert (fyi) markiert.
    """
    dup = await _find_duplicate_open_task(db, meta)
    if dup is not None:
        await _append_duplicate_note(db, dup, meta)
        if job_id is not None:
            await db.execute(
                update(EmailTriage)
                .where(EmailTriage.agent_job_id == job_id)
                .values(
                    triage_class="fyi",
                    reply_expected=False,
                    suggested_action={
                        "label": "Duplikat",
                        "triage_class": "fyi",
                        "deduplicated": True,
                        "duplicate_of": str(dup.id),
                        "rationale": (
                            f"Bereits als offene Aufgabe erfasst ('{(dup.title or '')[:60]}'). "
                            "Als weitere Meldung angedockt -- kein neuer Task."
                        ),
                    },
                    status="acted",
                )
            )
        logger.info(
            "Job %s: Duplikat erkannt -> an offenen Task %s angedockt (kein neuer Task)",
            job_id, dup.id,
        )
        return dup

    proj_result = await db.execute(
        select(Project).where(Project.status != "archived").order_by(Project.name)
    )
    projects = list(proj_result.scalars().all())
    matched_project = _match_project(suggested_project, projects)
    if not matched_project and projects:
        matched_project = projects[0]
    if not matched_project:
        logger.warning("Job %s: Kein Projekt fuer Task vorhanden", job_id)
        return None

    col_result = await db.execute(
        select(BoardColumn)
        .where(BoardColumn.project_id == matched_project.id)
        .order_by(BoardColumn.position)
        .limit(1)
    )
    first_col = col_result.scalar_one_or_none()
    if not first_col:
        logger.warning("Job %s: Projekt '%s' hat keine Board-Spalte", job_id, matched_project.name)
        return None

    pipeline_col_id = _determine_pipeline_column(deadline)
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
    next_pos = (max_pos_result.scalar_one_or_none() or 0) + 1

    # Nutzersichtbare Beschreibung saeubern (interne API-/Fehler-Diagnosen raus)
    # und immer mit einem Quell-E-Mail-Block (Von/Betreff/Deeplink) abschliessen,
    # damit jede E-Mail-Task die Herkunft + einen Link zur Original-Mail traegt.
    base_desc = _strip_internal_notes(task_description) or f"Erstellt aus E-Mail: {meta.get('subject', '')}"
    full_desc = base_desc + _email_reference_block(meta)

    new_task = Task(
        title=task_title,
        description=full_desc,
        project_id=matched_project.id,
        board_column_id=first_col.id,
        board_position=next_pos,
        pipeline_column_id=pipeline_col_id,
        email_message_id=meta.get("email_message_id"),
        email_conversation_id=meta.get("conversation_id"),
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
    return new_task


async def _structured_triage_reask(meta: dict, content: str) -> dict | None:
    """Tool-freier, parse-garantierter Klassifikations-Call (Structured Output).

    Rettungspfad, wenn der agentische Triage-Loop keinen verwertbaren JSON-Block
    lieferte: EIN direkter Ollama-Call mit ``response_format={"type":"json_object"}``
    (parse-garantiert) leitet die finale Klassifikation aus Betreff/Absender/Vorschau
    plus der bisherigen Agenten-Analyse ab. Bewusst OHNE Agent/Tools -- so gibt es
    keine Kollision mit dem Tool-Calling (``request_overrides`` wuerde sonst jeden
    Turn erzwingen und Tool-Aufrufe brechen).

    Best-effort: gibt None zurueck, wenn deaktiviert, das Triage-Modell nicht lokal
    ist oder der Call scheitert -- der Aufrufer faellt dann fail-closed zurueck.
    """
    cfg = get_settings()
    if not cfg.triage_structured_fallback or not _is_local_model(cfg.triage_model):
        return None
    subject = meta.get("subject", "")
    from_addr = meta.get("from_address", "")
    preview = (meta.get("body_preview") or "")[:500]
    analysis = (content or "")[-1500:]
    schema_hint = (
        '{"rationale": "kurz", "label": "kurzes Label", '
        '"triage_class": "task|auto_reply|fyi", "reply_expected": true|false, '
        '"confidence": 0.0}'
    )
    system_msg = (
        "Du bist ein E-Mail-Triage-Klassifikator. Gib AUSSCHLIESSLICH ein JSON-Objekt "
        f"nach diesem Schema zurueck: {schema_hint}. Begruende ZUERST (rationale), dann "
        "klassifiziere. triage_class ist genau eines von task, auto_reply, fyi. "
        "Terminzusagen/reine Infos sind fyi. Im Zweifel fyi."
    )
    user_msg = (
        f"Betreff: {subject}\nVon: {from_addr}\nVorschau: {preview}\n\n"
        f"Bisherige (ggf. unstrukturierte) Analyse des Agenten:\n{analysis}\n\n"
        "Leite daraus die finale Klassifikation als JSON ab."
    )
    model = cfg.triage_model.removeprefix("ollama/")
    url = f"{cfg.ollama_base_url.rstrip('/')}/v1/chat/completions"
    base_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0,
        "stream": False,
    }

    async def _call(response_format: dict) -> dict | None:
        payload = {**base_payload, "response_format": response_format}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url, json=payload, headers={"Authorization": "Bearer ollama"}
            )
            resp.raise_for_status()
            data = resp.json()
        msg = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
        parsed = _loads_lenient(msg)
        if isinstance(parsed, dict) and parsed.get("triage_class") in ("task", "auto_reply", "fyi"):
            return parsed
        return None

    # 1) Schema-constrained Decoding (Best Practice): erzwingt gueltiges JSON mit
    #    triage_class-Enum. Das rationale-Feld steht ZUERST -> das Modell committet
    #    erst die Begruendung, dann die Klasse ("reasoning before answer").
    json_schema_rf = {
        "type": "json_schema",
        "json_schema": {
            "name": "email_triage",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "rationale": {"type": "string"},
                    "label": {"type": "string"},
                    "triage_class": {
                        "type": "string",
                        "enum": ["task", "auto_reply", "fyi"],
                    },
                    "reply_expected": {"type": "boolean"},
                    "confidence": {"type": "number"},
                },
                "required": ["rationale", "triage_class", "reply_expected"],
                "additionalProperties": False,
            },
        },
    }
    try:
        parsed = await _call(json_schema_rf)
        if parsed is not None:
            return parsed
    except Exception:  # noqa: BLE001 - z.B. 400 bei aelterer Ollama-Version ohne json_schema
        logger.info(
            "Structured-Reask: json_schema nicht unterstuetzt, Graceful-Fallback json_object"
        )

    # 2) Graceful-Fallback auf das schwaechere json_object-Mode (aeltere Ollama-
    #    Versionen), damit ein fehlendes json_schema-Feature keinen Hard-Break gibt.
    try:
        return await _call({"type": "json_object"})
    except Exception:  # noqa: BLE001 - best-effort
        logger.warning("Structured-Triage-Reask fehlgeschlagen")
    return None


async def _fallback_unparsed_triage(job_id, meta: dict, moved_id: str | None = None) -> str:
    """Sicherheitsnetz, wenn der LLM keinen verwertbaren Triage-Block lieferte.

    Fail-closed (Best Practice): Bei Unsicherheit wird NICHT gehandelt. Die E-Mail
    wird als ``fyi`` mit ``needs_review``-Marker eingeordnet und bleibt -- via
    ``_finalize_email_state`` -- ungelesen in der Inbox sichtbar. Es wird KEIN
    Auto-Task mehr erstellt: ein faelschlich angelegter Task (z. B. aus einer
    blossen Terminzusage) ist teurer und nerviger als eine sichtbare Mail, die
    der Mensch in der Inbox ohnehin sieht und bei Bedarf manuell einordnet.
    """
    logger.warning(
        "Job %s: Kein verwertbarer JSON-Block -- fail-closed auf fyi/needs_review (kein Auto-Task)",
        job_id,
    )
    async with async_session() as db:
        await db.execute(
            update(EmailTriage)
            .where(EmailTriage.agent_job_id == job_id)
            .values(
                triage_class="fyi",
                reply_expected=False,
                confidence=None,
                suggested_action={
                    "label": "Unklar",
                    "triage_class": "fyi",
                    "needs_review": True,
                    "rationale": (
                        "Agent lieferte keinen strukturierten Triage-Block. Die E-Mail "
                        "bleibt zur manuellen Sichtung ungelesen in der Inbox -- kein Auto-Task."
                    ),
                    "fallback": True,
                },
                status="acted",
            )
        )
        await db.commit()
    # Auch im Fallback deterministisch finalisieren: Sentinel "Unklassifiziert"
    # ueberspringt das Kategorie-Setzen (kein Raten einer Outlook-Kategorie),
    # die Mail wird aber auf ungelesen zurueckgesetzt und bleibt sichtbar.
    await _finalize_email_state(meta, "Unklassifiziert", moved_id)
    return "completed"


async def _post_process_triage(
    job_id,
    content: str,
    meta: dict,
    captured_draft_id: str | None = None,
    tools_used: list[str] | None = None,
    moved_id: str | None = None,
) -> str:
    """Deterministische Post-Processing-Logik nach LLM-Klassifikation.

    ``captured_draft_id`` ist die echte Outlook-Draft-ID, die der Worker direkt aus
    dem ``create_draft``-Tool-Ergebnis erfasst hat (ground truth). Sie hat IMMER
    Vorrang vor einer im JSON-Block gemeldeten ID -- letztere wird vom LLM bei
    langen Graph-IDs regelmaessig verstuemmelt und ist deshalb nicht vertrauenswuerdig.

    ``tools_used`` (tatsaechlich aufgerufene Tools) dient dem Kontext-Gate: ein
    ``auto_reply`` ohne geladene Pflicht-Kontexte (Thread/History/Profil/Stil-Anker)
    wird auf ``task`` heruntergestuft, da solche Entwuerfe erfahrungsgemaess
    tonal/inhaltlich unbrauchbar sind.
    """
    parsed = _extract_json_block(content)
    if parsed is None:
        # Rettung vor dem Fail-Closed: EIN tool-freier, parse-garantierter
        # Klassifikations-Call (nur wenn aktiviert + lokales Modell).
        parsed = await _structured_triage_reask(meta, content)
        if parsed is not None:
            logger.info(
                "Job %s: Klassifikation via Structured-Fallback gerettet (%s)",
                job_id,
                parsed.get("triage_class"),
            )
            parsed.setdefault("task_title", meta.get("subject"))
        else:
            return await _fallback_unparsed_triage(job_id, meta, moved_id)

    triage_class = parsed.get("triage_class")
    label = parsed.get("label")
    # Echte Draft-ID aus dem Tool-Ergebnis ist die einzige verlaessliche Quelle.
    # Die vom Modell im JSON gemeldete ID wird NICHT als ID-Quelle genutzt.
    draft_id = captured_draft_id
    llm_claimed_draft = bool(parsed.get("draft_id"))
    if llm_claimed_draft and not captured_draft_id:
        logger.warning(
            "Job %s: LLM meldet draft_id, aber kein echtes create_draft-Tool-Ergebnis "
            "erfasst -- ID wird verworfen (kein verlaesslicher Entwurf).",
            job_id,
        )
    deadline = parsed.get("deadline")
    task_title = parsed.get("task_title")
    task_description = parsed.get("task_description")
    suggested_project = parsed.get("suggested_project")
    rationale = parsed.get("rationale")
    reply_expected = bool(parsed.get("reply_expected", False))

    # Sicherheitsgrad der Einschaetzung (0..1). Optional vom LLM geliefert; auf
    # gueltigen Bereich begrenzen, damit das Frontend ein verlaessliches Signal
    # (ConfidenceBadge) anzeigen kann.
    confidence = parsed.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
        if confidence is not None:
            if confidence > 1:  # toleriere Prozentangaben (z. B. 85)
                confidence = confidence / 100.0
            confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = None

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

    # Zwei-Pass-Entwurf: Der Klassifikations-Lauf hat (per Design) keinen Entwurf
    # erstellt. Sobald auto_reply feststeht, schreibt jetzt ein separater,
    # fokussierter Schreib-Pass den Draft mit Prosa-Sampling. Scheitert er, greift
    # unten der Fail-closed-Pfad. forced_class='task' bleibt unberührt.
    if (
        triage_class == "auto_reply"
        and not draft_id
        and get_settings().two_pass_draft
    ):
        draft_id = await _generate_reply_draft(meta)
        if draft_id:
            # Tools des Schreib-Passes fürs Kontext-Gate mitzählen (get_email/
            # get_thread/search_my_replies liefen erst jetzt).
            tools_used = sorted(_job_tool_names)
            logger.info("Job %s: Zwei-Pass-Draft erstellt (draft_id=%s)", job_id, draft_id)
        else:
            logger.warning("Job %s: Zwei-Pass-Draft lieferte keinen Entwurf", job_id)

    if triage_class == "auto_reply" and not draft_id:
        # Fail-closed (Best Practice): ohne echten Entwurf wird NICHT als Task
        # gehandelt, sondern als fyi belassen. Die Mail bleibt via
        # _finalize_email_state ungelesen in der Inbox sichtbar -- ein
        # faelschlich erstellter Task ist teurer als eine sichtbare Mail.
        logger.warning("Job %s: auto_reply ohne draft_id -> fyi (fail-closed, kein Auto-Task)", job_id)
        triage_class = "fyi"

    # Kontext-Gate (NICHT-destruktiv): Ein bereits ERSTELLTER Entwurf wird NIE
    # mehr verworfen. Frueher wurde bei fehlendem Pflicht-Kontext auf 'task'
    # heruntergestuft und draft_id genullt -- das liess gute Entwuerfe in Outlook
    # verwaisen und zeigte im Cockpit nur eine Task mit "ging nicht"-Notiz. Jeder
    # Entwurf bleibt jetzt als auto_reply zur HITL-Freigabe sichtbar; fehlender
    # Kontext senkt nur die angezeigte Confidence und wird INTERN vermerkt (nicht
    # im nutzersichtbaren Text). forced_class bleibt unberuehrt.
    gate_internal_note: str | None = None
    if (
        triage_class == "auto_reply"
        and draft_id
        and tools_used is not None
        and forced_class != "auto_reply"
    ):
        grade = _compute_self_grade(meta, {"draft_id": draft_id}, list(tools_used))
        if grade["missing"]:
            logger.info(
                "Job %s: auto_reply mit unvollstaendigem Pflicht-Kontext %s -- "
                "Entwurf bleibt erhalten, Confidence gesenkt (kein Downgrade)",
                job_id, grade["missing"],
            )
            capped = 0.4
            confidence = capped if confidence is None else min(confidence, capped)
            gate_internal_note = (
                "Entwurf ohne vollstaendigen Pflicht-Kontext erstellt "
                f"(fehlend: {', '.join(grade['missing'])}) -- vor Freigabe pruefen."
            )

    if triage_class == "task" and not task_title:
        task_title = meta.get("subject", "E-Mail Triage (kein Titel)")
        logger.warning("Job %s: task ohne task_title, verwende Subject: %s", job_id, task_title)

    # Low-Confidence-Gate (Best-Practice-Audit-Bucket): Eine Klassifikation mit
    # geringer Sicherheit wird zur menschlichen Sichtung markiert, statt still
    # durchzugehen. Nicht-destruktiv -- die Klasse bleibt, nur das needs_review-
    # Signal wird gesetzt, damit das Cockpit solche Faelle hervorhebt.
    low_conf_threshold = get_settings().triage_low_confidence_threshold
    needs_review = confidence is not None and confidence < low_conf_threshold
    if needs_review:
        logger.info(
            "Job %s: Confidence %.2f < %.2f -- als needs_review markiert",
            job_id, confidence, low_conf_threshold,
        )

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
                confidence=confidence,
                suggested_action={
                    "label": label,
                    "triage_class": triage_class,
                    "reply_expected": reply_expected,
                    "deadline": deadline,
                    "task_title": task_title,
                    "suggested_project": suggested_project,
                    "draft_id": draft_id,
                    "rationale": rationale,
                    "confidence": confidence,
                    "needs_review": needs_review,
                },
                status="acted" if triage_class != "auto_reply" else "processing",
            )
        )

        final_status = "completed"

        if triage_class == "task" and task_title:
            await _create_email_task(
                db,
                job_id,
                meta,
                task_title=task_title,
                task_description=task_description,
                suggested_project=suggested_project,
                deadline=deadline,
                reply_expected=reply_expected,
            )

        elif triage_class == "auto_reply" and draft_id:
            job_result = await db.execute(select(AgentJob).where(AgentJob.id == job_id))
            job = job_result.scalar_one_or_none()
            if job:
                existing_meta = dict(job.metadata_json or {})
                existing_meta["draft_id"] = draft_id
                # Lesbares "Warum" + Sicherheit fuer die Freigabe-Karte mitgeben,
                # damit das Frontend nicht den rohen Trace interpretieren muss.
                if rationale:
                    existing_meta["rationale"] = rationale
                if confidence is not None:
                    existing_meta["confidence"] = confidence
                if gate_internal_note:
                    existing_meta["context_warning"] = gate_internal_note
                existing_meta["summary"] = (
                    rationale
                    or f"Antwort-Entwurf für '{meta.get('subject') or '(kein Betreff)'}' vorbereitet."
                )
                # Original-Entwurf als Referenz fuer den spaeteren Stil-Diff snapshotten.
                snapshot = await _snapshot_agent_draft(draft_id)
                # Deterministisch erzwingen, dass der Entwurf im Original-Thread
                # liegt (Reply-All) -- unabhaengig davon, ob das LLM reply_to_id
                # gesetzt hat. Repariert ggf. die draft_id + Snapshot.
                draft_id, snapshot = await _ensure_draft_in_thread(
                    draft_id, meta.get("email_message_id", ""), snapshot
                )
                existing_meta["draft_id"] = draft_id
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

    # Deterministische Outlook-Finalisierung NACH der DB-Transaktion (reine Netz-
    # I/O): Kategorie-Sicherheitsnetz + Mail immer auf ungelesen zuruecksetzen.
    # Laeuft fuer alle Klassen (task/auto_reply/fyi) und auf der finalen ID.
    await _finalize_email_state(meta, label, moved_id)

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


def _draft_sampling_overrides(disable_thinking: bool = True) -> dict:
    """Prosa-Sampling fuer den Schreib-Pass (Qwen-3.6-Instruct-Empfehlung).

    ``temperature``/``top_p``/``presence_penalty`` gehen als Standard-Chat-Parameter,
    ``top_k`` provider-spezifisch via ``extra_body``. ``enable_thinking=False`` passt
    zur Instruct-Empfehlung (die Prosa-Params sind fuer den Nicht-Thinking-Modus
    gedacht) und haelt den Schreib-Pass schnell.
    """
    cfg = get_settings()
    extra: dict = {"top_k": cfg.draft_top_k}
    if disable_thinking:
        extra["chat_template_kwargs"] = {"enable_thinking": False}
    return {
        "temperature": cfg.draft_temperature,
        "top_p": cfg.draft_top_p,
        "presence_penalty": cfg.draft_presence_penalty,
        "extra_body": extra,
    }


def _run_agent_sync(
    agent, prompt: str, disable_thinking: bool, overrides: dict | None = None
) -> str:
    """Synchroner Agent-Lauf (im Thread). Gibt den finalen Antworttext zurueck.

    ``disable_thinking`` setzt SOTA-korrekt ``extra_body.chat_template_kwargs``;
    standardmaessig False (Thinking an). ``overrides`` erlaubt vollstaendige
    ``request_overrides`` (z. B. Prosa-Sampling im Draft-Pass) und hat Vorrang --
    der Aufrufer ist dann fuer den Thinking-Schalter im ``extra_body`` zustaendig.
    """
    prev_overrides = getattr(agent, "request_overrides", None)
    req: dict | None = None
    if overrides is not None:
        req = dict(overrides)
    elif disable_thinking:
        req = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    if req is not None:
        agent.request_overrides = req
    try:
        result = agent.run_conversation(prompt, system_message=WORKER_SYSTEM_PROMPT)
    finally:
        if req is not None:
            agent.request_overrides = prev_overrides

    if isinstance(result, dict):
        return str(result.get("final_response") or "")
    return str(result or "")


async def _generate_reply_draft(meta: dict) -> str | None:
    """Zweiter, fokussierter Schreib-Pass (nur bei ``two_pass_draft``).

    Erzeugt den Antwort-Entwurf in einem eigenen Agenten-Lauf mit Prosa-Sampling,
    getrennt von der Klassifikation. Best-effort: liefert die echte create_draft-ID
    (ground truth aus dem Tool-Callback) oder ``None``. Bei ``None`` greift im
    Post-Processing der bestehende Fail-closed-Pfad (auto_reply ohne Draft -> fyi).
    """
    global _job_created_draft_id
    if _agent is None:
        logger.warning("Zwei-Pass-Draft: kein Worker-Agent verfügbar")
        return None
    try:
        prompt = await _build_draft_prompt(meta)
    except Exception:  # noqa: BLE001 - best-effort
        logger.exception("Zwei-Pass-Draft: Prompt-Bau fehlgeschlagen")
        return None
    # Nur den in DIESEM Pass erstellten Entwurf erfassen.
    _job_created_draft_id = None
    try:
        await asyncio.to_thread(
            _run_agent_sync, _agent, prompt, True, _draft_sampling_overrides(True)
        )
    except Exception:  # noqa: BLE001 - best-effort
        logger.exception("Zwei-Pass-Draft: Schreib-Pass fehlgeschlagen")
        return None
    return _job_created_draft_id


def _enforce_autonomy_status(meta: dict, content: str) -> str:
    """Bestimmt den End-Status nach Autonomie-Stufe statt per Text-Heuristik.

    - **L0 Block**: nicht ausführen -> ``blocked`` (Defensive; L0 sollte den
      Worker gar nicht erreichen, da Trigger/Scheduler L0 sperren).
    - **L1 Freigabe**: immer ``awaiting_approval`` (Entwurf, nie Auto-Versand).
    - **L2 Melden**: ``completed`` + post-hoc Benachrichtigung.
    - **L3 Auto**: autonom ``completed``.

    Ohne Autonomie-Kontext (Alt-Jobs/sonstige Typen) gilt die bisherige
    Heuristik (``awaiting_approval``, wenn das Modell es signalisiert).
    """
    autonomy = (meta or {}).get("autonomy_level")
    if autonomy == "L0":
        return "blocked"
    if autonomy == "L1":
        return "awaiting_approval"
    if autonomy in ("L2", "L3"):
        return "completed"
    return "awaiting_approval" if "awaiting_approval" in content.lower() else "completed"


async def _process_job(agent, job_id, job_type: str, prompt: str, meta: dict) -> None:
    """Verarbeitet einen einzelnen AgentJob via Hermes AIAgent."""
    global _job_trace, _job_created_draft_id, _job_moved_message_id
    logger.info("Starte Job %s (type=%s)", job_id, job_type)

    async with async_session() as db:
        await db.execute(
            update(AgentJob)
            .where(AgentJob.id == job_id)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await db.commit()

    _job_trace = []
    _job_created_draft_id = None
    _job_moved_message_id = None
    _job_tool_names.clear()
    disable_thinking = _thinking_disabled(job_type, meta.get("skill"))

    # Token-Verbrauch pro Job messen: der persistente Agent zaehlt kumulativ
    # (session_total_tokens) -- die Differenz vor/nach dem Lauf ist der Verbrauch
    # dieses Jobs. Grundlage fuer Kosten-/Kontext-Observability im Cockpit.
    tokens_before = int(getattr(agent, "session_total_tokens", 0) or 0)

    try:
        content = await asyncio.to_thread(_run_agent_sync, agent, prompt, disable_thinking)
        # Echte Draft-ID aus dem Tool-Ergebnis (ground truth) an das Post-Processing
        # weiterreichen -- die vom LLM gemeldete ID wird bewusst ignoriert.
        captured_draft_id = _job_created_draft_id
        captured_moved_id = _job_moved_message_id
        logger.info("Job %s abgeschlossen: %s", job_id, content[:200])

        if job_type == "email_triage":
            # Zuverlaessigkeit: Liefert der erste Lauf keinen verwertbaren JSON-Block,
            # genau EIN strikter Nachfass-Prompt, bevor das Fallback-Netz greift.
            if _extract_json_block(content) is None:
                logger.info("Job %s: kein JSON-Block -- strikter Nachfass-Lauf", job_id)
                retry = await asyncio.to_thread(
                    _run_agent_sync, agent, _json_retry_prompt(content), disable_thinking
                )
                if retry and _extract_json_block(retry) is not None:
                    content = f"{content}\n\n{retry}"
            trace = list(_job_trace)
            # tools_used aus der ungekappten Tool-Namen-Menge (nicht aus dem
            # 200-Event-Trace) -- sonst fehlen spaete Tools wie create_draft/
            # search_my_replies und das Kontext-Gate stuft faelschlich herunter.
            tools_used = sorted(_job_tool_names)
            status = await _post_process_triage(
                job_id, content, meta, captured_draft_id, tools_used, captured_moved_id
            )
            # Nach dem Post-Processing neu erfassen: ein evtl. Zwei-Pass-Schreib-Pass
            # hat weitere Tools (get_email/get_thread/search_my_replies/create_draft)
            # aufgerufen -- fuer korrekte Observability/Self-Grade mitzaehlen.
            tools_used = sorted(_job_tool_names)
        elif job_type == "chat_triage":
            trace = list(_job_trace)
            tools_used = sorted(_job_tool_names)
            status = await _post_process_chat_triage(job_id, content)
        else:
            trace = list(_job_trace)
            tools_used = sorted(_job_tool_names)
            status = _enforce_autonomy_status(meta, content)

        if job_type != "email_triage":
            if status == "awaiting_approval":
                async with async_session() as notif_db:
                    await notify_agent_awaiting_approval(notif_db, job_id=job_id)
                    await notif_db.commit()
            elif status == "completed" and (meta or {}).get("autonomy_level") == "L2":
                # L2 'Melden': autonom ausgeführt, Mensch post-hoc informieren.
                async with async_session() as notif_db:
                    await notify_agent_completed(notif_db, job_id=job_id)
                    await notif_db.commit()

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
            tokens_after = int(getattr(agent, "session_total_tokens", 0) or 0)
            tokens_used = tokens_after - tokens_before
            job_values = {
                "status": status,
                "output": content[:16000],
                "metadata_json": new_meta,
                "completed_at": datetime.now(timezone.utc),
            }
            if tokens_used > 0:
                job_values["tokens_used"] = tokens_used
                # Lokale Ollama-Modelle verursachen keine API-Kosten.
                job_values["cost_usd"] = 0
            await db.execute(
                update(AgentJob).where(AgentJob.id == job_id).values(**job_values)
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
            elif job_type == "chat_triage":
                await db.execute(
                    update(ChatTriage)
                    .where(ChatTriage.agent_job_id == job_id)
                    .values(triage_class="fyi", status="dismissed")
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
            except httpx.HTTPStatusError as exc:
                # NUR ein echtes 404 bedeutet "Entwurf wirklich weg" (gesendet/
                # geloescht). Alles andere (5xx, Drosselung, Netz) ist transient und
                # darf eine gueltige Freigabe NICHT zerstoeren.
                if exc.response.status_code != 404:
                    logger.warning(
                        "Draft-Cleanup: transienter Fehler (%s) fuer Job %s -- bleibt awaiting_approval",
                        exc.response.status_code, job.id,
                    )
                    continue
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
                logger.info("Draft-Cleanup: Job %s automatisch abgeschlossen (Draft 404 -- nicht mehr in Outlook)", job.id)
            except Exception:
                # Unklarer Fehler (Timeout, Verbindungsabbruch, ...) -> Job bewusst
                # NICHT abschliessen; im naechsten Zyklus erneut pruefen.
                logger.warning(
                    "Draft-Cleanup: get_email fehlgeschlagen (kein 404) fuer Job %s -- bleibt awaiting_approval",
                    job.id,
                )
                continue
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


async def _resweep_unclassified_triages(limit: int = 20) -> int:
    """Holt still durchgefallene Triages zurueck in die Queue (Selbstheilung).

    E-Mails, deren Agent-Job abgeschlossen/fehlgeschlagen ist, deren
    ``email_triage`` aber ohne Klasse auf ``pending`` haengt (z. B. aus der Zeit
    vor dem robusten Parser, oder weil der LLM keinen Block lieferte), werden mit
    geklonter Metadata neu eingereiht. Ein ``resweep_count`` deckelt die
    Wiederholungen (``MAX_RESWEEP``), damit dauerhaft problematische Mails nicht
    endlos zirkulieren.
    """
    requeued = 0
    dismissed = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=RESWEEP_MAX_AGE_DAYS)
    async with async_session() as db:
        rows = await db.execute(
            select(EmailTriage, AgentJob)
            .join(AgentJob, EmailTriage.agent_job_id == AgentJob.id)
            .where(
                EmailTriage.triage_class.is_(None),
                EmailTriage.status == "pending",
                AgentJob.status.in_(["completed", "failed"]),
                # Nur frische Mails -- aeltere 404en ohnehin und erzeugen nur Churn.
                EmailTriage.created_at >= cutoff,
            )
            .order_by(EmailTriage.created_at.desc())
            .limit(limit)
        )
        for triage, job in rows.all():
            meta = dict(job.metadata_json or {})
            # Ohne Message-ID ist ein Re-Run sinnlos (get_email schluege fehl).
            if not meta.get("email_message_id"):
                triage.status = "dismissed"
                dismissed += 1
                continue
            resweep_count = int(meta.get("resweep_count") or 0)
            if resweep_count >= MAX_RESWEEP:
                # Erschoepfte Wiederholungen: endgueltig schliessen, statt jeden
                # Zyklus erneut zu selektieren (kein Dauer-Churn).
                triage.status = "dismissed"
                dismissed += 1
                continue
            new_meta = {
                k: v for k, v in meta.items()
                if k not in ("trace", "tools_used", "self_grade")
            }
            new_meta["resweep_count"] = resweep_count + 1
            new_meta["resweep_of"] = str(job.id)
            new_job = AgentJob(
                task_id=None,
                job_type="email_triage",
                status="queued",
                llm_model=job.llm_model,
                metadata_json=new_meta,
            )
            db.add(new_job)
            await db.flush()
            triage.agent_job_id = new_job.id
            triage.status = "pending"
            requeued += 1
        if requeued or dismissed:
            await db.commit()
            logger.info(
                "Resweep: %d Triage(s) neu eingereiht, %d endgueltig geschlossen",
                requeued, dismissed,
            )
    return requeued


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
    last_resweep = time.monotonic()

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

            if time.monotonic() - last_resweep >= RESWEEP_INTERVAL:
                try:
                    await _resweep_unclassified_triages()
                except Exception:
                    logger.exception("Resweep fehlgeschlagen")
                last_resweep = time.monotonic()

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

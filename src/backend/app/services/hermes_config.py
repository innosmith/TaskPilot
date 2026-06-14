"""Generiert die Hermes-Runtime-Konfiguration (~/.hermes/config.yaml).

Hermes liest MCP-Server, Modell und Kontextfenster aus ``~/.hermes/config.yaml``.
``${VAR}``-Platzhalter in den ``env``-Blöcken werden von Hermes zur Discovery-Zeit
aus ``os.environ`` aufgelöst (siehe ``tools.mcp_tool._load_mcp_config``). Hermes'
``_build_safe_env`` reicht ausschliesslich die explizit in ``env`` aufgeführten
Werte an die MCP-Subprozesse weiter — Secrets müssen daher dort referenziert sein.

Strategie:
- Secrets bleiben als ``${TP_*}``-Platzhalter in der YAML (kein Klartext auf der Platte).
- ``populate_hermes_env()`` befüllt ``os.environ`` aus den DB-Settings (Owner) bzw.
  den Pydantic-Settings, bevor die Discovery läuft.
- Pfade (Python-Binary, MCP-Basisverzeichnis) werden konkret aufgelöst, damit
  dieselbe Logik in Dev (lokale venv) und Prod (Container, /app) funktioniert.
"""

import logging
import os
import sys
from pathlib import Path

import yaml
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session

logger = logging.getLogger("taskpilot.hermes_config")


def get_hermes_home() -> Path:
    """Liefert das Hermes-Home (config.yaml, skills/, memories/, SOUL.md)."""
    return Path(os.path.expanduser(get_settings().hermes_home))


def _parse_skill_frontmatter(content: str) -> dict:
    """Liest das YAML-Frontmatter eines SKILL.md (zwischen den ``---``-Zeilen)."""
    import yaml

    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    raw = content[3:end]
    try:
        data = yaml.safe_load(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _first_body_line(content: str) -> str:
    """Erste nicht-leere, nicht-Heading-Zeile als Fallback-Beschreibung.

    Ueberspringt ein etwaiges YAML-Frontmatter (Block zwischen zwei ``---``-Zeilen).
    """
    lines = content.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    for line in lines[start:]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped != "---":
            return stripped[:200]
    return ""


def discover_skills() -> list[dict]:
    """Erkennt die Hermes-Skills im ``skills/``-Verzeichnis.

    Hermes-nativ liegen Skills als ``skills/<name>/SKILL.md`` mit YAML-Frontmatter
    (``name``, ``description``, ``metadata.hermes.requires_toolsets``). Diese Funktion
    ist die Single Source of Truth fuer alle Skill-Listings im Frontend (Intelligenz-
    Tab, Heartbeat, Brain). Faellt auf alte Flat-``.md``-Dateien zurueck, falls (noch)
    keine nativen Skills vorhanden sind.

    Returns: Liste von Dicts mit ``name``, ``description``, ``requires_toolsets``,
    ``content`` und ``size``, sortiert nach Name.
    """
    skills_dir = get_hermes_home() / "skills"
    if not skills_dir.exists():
        return []

    out: list[dict] = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            content = skill_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = _parse_skill_frontmatter(content)
        name = str(fm.get("name") or skill_file.parent.name).strip()
        description = str(fm.get("description") or _first_body_line(content)).strip()
        hermes_meta = (fm.get("metadata") or {}).get("hermes") or {}
        req = hermes_meta.get("requires_toolsets") or []
        if not isinstance(req, list):
            req = [str(req)]
        try:
            size = skill_file.stat().st_size
        except OSError:
            size = len(content.encode("utf-8"))
        out.append({
            "name": name,
            "description": description,
            "requires_toolsets": [str(t) for t in req],
            "content": content,
            "size": size,
        })

    # Fallback: alte Flat-Skills (skills/<name>.md), nur wenn keine nativen da sind.
    if not out:
        for f in sorted(skills_dir.glob("*.md")):
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            out.append({
                "name": f.stem,
                "description": _first_body_line(content),
                "requires_toolsets": [],
                "content": content,
                "size": f.stat().st_size,
            })

    out.sort(key=lambda s: s["name"])
    return out


def _mcp_base_dir() -> str:
    """Verzeichnis, das die ``mcp-*``-Server enthält (Dev: ``src/``, Prod: ``/app``)."""
    override = os.environ.get("TP_MCP_BASE_DIR")
    if override:
        return override
    # services/hermes_config.py -> parents[3] == <repo>/src
    return str(Path(__file__).resolve().parents[3])


def _python_bin() -> str:
    """Python-Interpreter für die MCP-Subprozesse (gleiche venv wie das Backend)."""
    return os.environ.get("TP_HERMES_PYTHON") or sys.executable


# Mapping Settings-Attribut -> Env-Var-Name, die die config.yaml referenziert.
# Reihenfolge: DB-Settings (Owner) haben Vorrang, sonst Pydantic-Settings (.env).
_DB_TOKEN_KEYS: dict[str, str] = {
    "pipedrive_api_token": "TP_PIPEDRIVE_API_TOKEN",
    "pipedrive_domain": "TP_PIPEDRIVE_DOMAIN",
    "toggl_api_token": "TP_TOGGL_API_TOKEN",
    "toggl_workspace_id": "TP_TOGGL_WORKSPACE_ID",
    "bexio_api_token": "TP_BEXIO_API_TOKEN",
    "invoiceinsight_api_key": "TP_INVOICEINSIGHT_API_KEY",
    "invoiceinsight_url": "TP_INVOICEINSIGHT_URL",
    "tavily_api_key": "TP_TAVILY_API_KEY",
}

# Settings-Attribut -> Env-Var, immer aus Pydantic-Settings (kein DB-Override).
_SETTINGS_KEYS: dict[str, str] = {
    "db_host": "TP_DB_HOST",
    "db_port": "TP_DB_PORT",
    "db_user": "TP_DB_USER",
    "db_password": "TP_DB_PASSWORD",
    "db_name": "TP_DB_NAME",
    "graph_tenant_id": "TP_GRAPH_TENANT_ID",
    "graph_client_id": "TP_GRAPH_CLIENT_ID",
    "graph_client_secret": "TP_GRAPH_CLIENT_SECRET",
    "graph_user_email": "TP_GRAPH_USER_EMAIL",
    "isi_host": "TP_ISI_HOST",
    "isi_db": "TP_ISI_DB",
    "isi_user": "TP_ISI_USER",
    "isi_secret": "TP_ISI_SECRET",
    "openai_api_key": "TP_OPENAI_API_KEY",
}


async def populate_hermes_env() -> None:
    """Setzt alle ``TP_*``-Env-Vars, die ``config.yaml`` referenziert, in ``os.environ``.

    Hermes löst die ``${VAR}``-Platzhalter zur Discovery-Zeit aus ``os.environ`` auf.
    Bereits gesetzte Env-Vars bleiben unangetastet (Container-Override gewinnt).
    """
    cfg = get_settings()

    for attr, env_key in _SETTINGS_KEYS.items():
        if os.environ.get(env_key):
            continue
        value = getattr(cfg, attr, "")
        os.environ[env_key] = str(value) if value not in (None, "") else ""

    # Sandbox-Image (optional)
    os.environ.setdefault("TP_SANDBOX_IMAGE", os.environ.get("TP_SANDBOX_IMAGE", ""))

    # DB-Settings des Owners haben für die Integrations-Tokens Vorrang.
    db_settings: dict = {}
    try:
        async with async_session() as db:
            from app.models import User

            result = await db.execute(
                select(User.settings).where(User.role == "owner").limit(1)
            )
            db_settings = result.scalar_one_or_none() or {}
    except Exception:
        logger.warning("Hermes-Env: DB-Settings nicht lesbar — nutze .env-Fallback")

    for db_key, env_key in _DB_TOKEN_KEYS.items():
        if os.environ.get(env_key):
            continue
        value = db_settings.get(db_key) or getattr(cfg, db_key, "")
        os.environ[env_key] = str(value) if value not in (None, "") else ""


def build_config_dict() -> dict:
    """Baut das Hermes-Config-Dict (Modell + 9 MCP-Server + contentConverter)."""
    cfg = get_settings()
    base = _mcp_base_dir()
    py = _python_bin()
    pythonpath = ":".join([
        base,
        f"{base}/email-graph",
        f"{base}/pipedrive",
        f"{base}/bexio",
        f"{base}/toggl",
    ])

    # Ollama /v1 (OpenAI-kompatibel) als custom-Provider — Spike-validiert.
    ollama_v1 = f"{cfg.ollama_base_url.rstrip('/')}/v1"

    def stdio(server_subdir: str, env: dict, extra_pythonpath: str | None = None) -> dict:
        pp = pythonpath if extra_pythonpath is None else extra_pythonpath
        return {
            "command": py,
            "args": [f"{base}/{server_subdir}/server.py"],
            "env": {**env, "PYTHONPATH": pp},
            "timeout": 120,
            "connect_timeout": 60,
        }

    mcp_servers: dict = {
        "taskpilot": stdio("mcp-taskpilot", {
            "TP_DB_HOST": "${TP_DB_HOST}",
            "TP_DB_PORT": "${TP_DB_PORT}",
            "TP_DB_USER": "${TP_DB_USER}",
            "TP_DB_PASSWORD": "${TP_DB_PASSWORD}",
            "TP_DB_NAME": "${TP_DB_NAME}",
        }),
        "graph": stdio("mcp-graph", {
            "GRAPH_TENANT_ID": "${TP_GRAPH_TENANT_ID}",
            "GRAPH_CLIENT_ID": "${TP_GRAPH_CLIENT_ID}",
            "GRAPH_CLIENT_SECRET": "${TP_GRAPH_CLIENT_SECRET}",
            "GRAPH_USER_EMAIL": "${TP_GRAPH_USER_EMAIL}",
        }, extra_pythonpath=f"{base}:{base}/email-graph"),
        "pipedrive": stdio("mcp-pipedrive", {
            "TP_PIPEDRIVE_API_TOKEN": "${TP_PIPEDRIVE_API_TOKEN}",
            "TP_PIPEDRIVE_DOMAIN": "${TP_PIPEDRIVE_DOMAIN}",
        }, extra_pythonpath=f"{base}:{base}/pipedrive"),
        "toggl": stdio("mcp-toggl", {
            "TP_TOGGL_API_TOKEN": "${TP_TOGGL_API_TOKEN}",
            "TP_TOGGL_WORKSPACE_ID": "${TP_TOGGL_WORKSPACE_ID}",
        }, extra_pythonpath=f"{base}:{base}/toggl"),
        "bexio": stdio("mcp-bexio", {
            "TP_BEXIO_API_TOKEN": "${TP_BEXIO_API_TOKEN}",
        }, extra_pythonpath=f"{base}:{base}/bexio"),
        "signa": stdio("mcp-signa", {
            "ISI_HOST": "${TP_ISI_HOST}",
            "ISI_DB": "${TP_ISI_DB}",
            "ISI_USER": "${TP_ISI_USER}",
            "ISI_SECRET": "${TP_ISI_SECRET}",
            "TP_OPENAI_API_KEY": "${TP_OPENAI_API_KEY}",
        }, extra_pythonpath=base),
        "invoiceinsight": stdio("mcp-invoiceinsight", {
            "TP_INVOICEINSIGHT_URL": "${TP_INVOICEINSIGHT_URL}",
            "TP_INVOICEINSIGHT_API_KEY": "${TP_INVOICEINSIGHT_API_KEY}",
        }, extra_pythonpath=base),
        "scripts": stdio("mcp-scripts", {
            "TP_SECRETS_DIR": os.environ.get("TP_SECRETS_DIR", os.path.expanduser("~/.secrets/taskpilot")),
            "TP_SCRIPTS_OUTPUT_DIR": "/tmp/taskpilot-scripts-output",
        }, extra_pythonpath=base),
        "sandbox": stdio("mcp-sandbox", {
            "TP_SANDBOX_IMAGE": "${TP_SANDBOX_IMAGE}",
            "TP_SANDBOX_OUTPUT_DIR": "/tmp/taskpilot-sandbox-output",
        }, extra_pythonpath=base),
        # Content-Converter (md -> docx/pptx). Binary nur im Docker-Image
        # vorhanden; in der Dev-Umgebung schlaegt die Discovery still fehl
        # (Hermes loggt eine Warnung und fahrt fort).
        "contentConverter": {
            "command": os.environ.get("TP_CONTENTCONVERTER_CCONV_BIN")
            or os.environ.get("TP_CCONV_BIN", "cconv"),
            "args": ["serve"],
            "env": {},
            "timeout": 120,
            "connect_timeout": 60,
        },
    }

    return {
        "model": {
            "default": cfg.triage_model.removeprefix("ollama/"),
            "provider": "custom",
            "base_url": ollama_v1,
            "api_key": "ollama",
            "api_mode": "chat_completions",
            "context_length": 131072,
        },
        # Built-in-Memory aktiv schalten: MEMORY.md + USER.md werden in den
        # System-Prompt injiziert (nur bei lokalen Modellen, da der Worker/Chat
        # fuer Cloud-Modelle skip_memory setzt). Kein externer Provider (Honcho):
        # die Built-in-Layer + die DB-gestuetzten Episoden/Regeln decken das ab.
        # Die *_char_limit-Werte sind Schreib-Budgets des memory-Tools, keine
        # harte Kuerzung beim Laden -- USER.md/MEMORY.md werden vollstaendig injiziert.
        "memory": {
            "memory_enabled": True,
            "user_profile_enabled": True,
            "nudge_interval": 10,
            "memory_char_limit": 2200,
            "user_char_limit": 1375,
            "provider": "",
        },
        # Skill-Selbstkuratierung: seltener zur Skill-Erstellung anstupsen,
        # damit Fachjobs (Triage) nicht durch Meta-Hinweise gestoert werden.
        "skills": {
            "creation_nudge_interval": 25,
        },
        # Kontext-Kompression: lange Threads/Chats werden ab 70 % des Kontext-
        # fensters zusammengefasst (die letzten 20 Turns bleiben unangetastet).
        "compression": {
            "enabled": True,
            "threshold": 0.7,
            "target_ratio": 0.3,
            "protect_last_n": 20,
        },
        # Hilfsmodelle fuer Nebenaufgaben (Kompression, Vision) laufen BEWUSST auf
        # demselben lokalen Hauptmodell. Begruendung: ein separates Modell wuerde in
        # Ollama Model-Loading/-Offloading ausloesen (zusaetzlicher RAM + Latenz) --
        # alles ueber das ohnehin geladene Hauptmodell ist effizienter und haelt die
        # Daten lokal. Explizit gesetzt (provider=custom + base_url), damit der
        # Endpoint inkl. Kontextfenster eindeutig ist und die Kompressions-
        # Feasibility-Pruefung beim Sessionstart nicht warnt.
        "auxiliary": {
            "compression": {
                "provider": "custom",
                "base_url": ollama_v1,
                "api_key": "ollama",
                "api_mode": "chat_completions",
                "model": cfg.triage_model.removeprefix("ollama/"),
                "context_length": 131072,
            },
            "vision": {
                "provider": "custom",
                "base_url": ollama_v1,
                "api_key": "ollama",
                "api_mode": "chat_completions",
                "model": cfg.triage_model.removeprefix("ollama/"),
                "context_length": 131072,
            },
        },
        # Tool-Loop-Guardrails: schuetzen vor Endlosschleifen/Token-Verbrennung.
        # Warnungen frueh, harte Stopps nach mehrfach identischem Fehlversuch bzw.
        # ergebnislosem Wiederholen idempotenter Tools.
        "tool_loop_guardrails": {
            "warnings_enabled": True,
            "hard_stop_enabled": True,
            "warn_after": {
                "exact_failure": 2,
                "same_tool_failure": 3,
                "idempotent_no_progress": 2,
            },
            "hard_stop_after": {
                "exact_failure": 4,
                "same_tool_failure": 8,
                "idempotent_no_progress": 4,
            },
        },
        "mcp_servers": mcp_servers,
    }


def write_hermes_config() -> Path:
    """Schreibt ``~/.hermes/config.yaml`` (Verzeichnisse werden angelegt)."""
    home = get_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    for sub in ("skills", "memories", "sessions", "logs"):
        (home / sub).mkdir(parents=True, exist_ok=True)

    config_path = home / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(build_config_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    logger.info("Hermes-Config geschrieben: %s", config_path)
    return config_path

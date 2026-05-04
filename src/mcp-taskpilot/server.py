"""TaskPilot MCP-Server — Hermes Agent kann Tasks und Agent-Jobs lesen/schreiben."""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

import asyncpg
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_taskpilot")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


async def _get_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        host=_env("TP_DB_HOST", "localhost"),
        port=int(_env("TP_DB_PORT", "5435")),
        user=_env("TP_DB_USER", "taskpilot"),
        password=_env("TP_DB_PASSWORD", "taskpilot_dev_2026"),
        database=_env("TP_DB_NAME", "taskpilot_dev"),
        min_size=1,
        max_size=3,
    )


TOOLS = [
    Tool(
        name="list_projects",
        description="Alle aktiven Projekte mit Board-Spalten auflisten",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="list_tasks",
        description="Tasks filtern nach Projekt, Assignee oder Status",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "UUID des Projekts"},
                "assignee": {"type": "string", "description": "'me' oder 'agent'"},
                "is_completed": {"type": "boolean"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    ),
    Tool(
        name="get_task",
        description="Ein Task mit Checkliste und Tags laden",
        inputSchema={
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "UUID des Tasks"}},
            "required": ["task_id"],
        },
    ),
    Tool(
        name="create_task",
        description="Neuen Task erstellen",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "project_id": {"type": "string"},
                "board_column_id": {"type": "string"},
                "description": {"type": "string"},
                "assignee": {"type": "string", "default": "me"},
                "pipeline_column_id": {"type": "string"},
                "due_date": {"type": "string", "description": "Faelligkeitsdatum im Format YYYY-MM-DD"},
                "recurrence_rule": {"type": "string", "description": "Cron-Ausdruck für Wiederholungen, z.B. '0 7 * * MON'"},
            },
            "required": ["title", "project_id", "board_column_id"],
        },
    ),
    Tool(
        name="update_task",
        description="Task aktualisieren (Titel, Beschreibung, Status etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "assignee": {"type": "string"},
                "is_completed": {"type": "boolean"},
                "due_date": {"type": "string", "description": "Faelligkeitsdatum im Format YYYY-MM-DD"},
                "recurrence_rule": {"type": "string", "description": "Cron-Ausdruck für Wiederholungen, z.B. '0 7 * * MON'"},
            },
            "required": ["task_id"],
        },
    ),
    Tool(
        name="get_agent_job",
        description="Details eines Agent-Jobs lesen",
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    ),
    Tool(
        name="list_agent_jobs",
        description="Agent-Jobs auflisten, optional nach Status filtern",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "queued, running, completed, failed, awaiting_approval"},
            },
        },
    ),
    Tool(
        name="update_agent_job",
        description="Agent-Job-Ergebnis schreiben (Status, Output, Tokens, Kosten)",
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "status": {"type": "string"},
                "output": {"type": "string"},
                "error_message": {"type": "string"},
                "llm_model": {"type": "string"},
                "tokens_used": {"type": "integer"},
                "cost_usd": {"type": "number"},
            },
            "required": ["job_id"],
        },
    ),
    Tool(
        name="get_sender_profile",
        description="Absender-Profil laden. Gibt gespeicherte Beziehungsinformationen zurück (Ton, Sprache, Beziehungstyp, Organisation). Falls kein Profil existiert, wird ein leeres Profil mit Defaults zurückgegeben.",
        inputSchema={
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "E-Mail-Adresse des Absenders"},
            },
            "required": ["email"],
        },
    ),
    Tool(
        name="update_sender_profile",
        description="Absender-Profil aktualisieren oder neu anlegen. Wird nach jeder Triage aufgerufen, um das Beziehungsgedaechtnis zu pflegen.",
        inputSchema={
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "E-Mail-Adresse des Absenders"},
                "display_name": {"type": "string"},
                "organization": {"type": "string", "description": "Firma/Organisation des Absenders"},
                "relationship": {"type": "string", "enum": ["kunde", "partner", "lieferant", "intern", "hochschule", "behoerde", "unbekannt"]},
                "tone": {"type": "string", "enum": ["formell", "informell", "neutral"]},
                "language": {"type": "string", "enum": ["de", "en", "fr", "it"]},
                "notes": {"type": "string", "description": "Freitext-Notizen zum Absender"},
            },
            "required": ["email"],
        },
    ),
    Tool(
        name="web_search",
        description="Websuche via Tavily API ausführen. Gibt relevante Suchergebnisse mit Titel, URL und Inhalt zurück. Nützlich für aktuelle Informationen, Faktencheck und Research.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff"},
                "search_depth": {"type": "string", "enum": ["basic", "advanced"], "default": "basic", "description": "basic = 1 Credit, advanced = 2 Credits (gruendlicher)"},
                "max_results": {"type": "integer", "default": 5, "description": "Maximale Anzahl Ergebnisse (1-10)"},
                "task_id": {"type": "string", "description": "Optional: UUID des zugehörigen Tasks"},
            },
            "required": ["query"],
        },
    ),
]

server = Server("taskpilot")
pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        pool = await _get_pool()
    return pool


def _row_to_dict(row: asyncpg.Record) -> dict:
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif hasattr(v, "hex"):
            d[k] = str(v)
    return d


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    p = await get_pool()

    if name == "list_projects":
        rows = await p.fetch(
            "SELECT id, name, color, status FROM projects WHERE status != 'archived' ORDER BY name"
        )
        result = [_row_to_dict(r) for r in rows]
        for proj in result:
            cols = await p.fetch(
                "SELECT id, name, position FROM board_columns WHERE project_id = $1 ORDER BY position",
                proj["id"] if not isinstance(proj["id"], str) else rows[result.index(proj)]["id"],
            )
            proj["board_columns"] = [_row_to_dict(c) for c in cols]
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "list_tasks":
        conditions = []
        params = []
        idx = 1
        if arguments.get("project_id"):
            conditions.append(f"t.project_id = ${idx}::uuid")
            params.append(arguments["project_id"])
            idx += 1
        if arguments.get("assignee"):
            conditions.append(f"t.assignee = ${idx}")
            params.append(arguments["assignee"])
            idx += 1
        if "is_completed" in arguments:
            conditions.append(f"t.is_completed = ${idx}")
            params.append(arguments["is_completed"])
            idx += 1

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        limit = arguments.get("limit", 50)
        rows = await p.fetch(
            f"SELECT t.id, t.title, t.assignee, t.is_completed, t.due_date, p.name as project_name "
            f"FROM tasks t JOIN projects p ON p.id = t.project_id {where} "
            f"ORDER BY t.created_at DESC LIMIT {limit}",
            *params,
        )
        return [TextContent(type="text", text=json.dumps([_row_to_dict(r) for r in rows], indent=2))]

    elif name == "get_task":
        row = await p.fetchrow(
            "SELECT t.*, p.name as project_name FROM tasks t "
            "JOIN projects p ON p.id = t.project_id WHERE t.id = $1::uuid",
            arguments["task_id"],
        )
        if row is None:
            return [TextContent(type="text", text="Task nicht gefunden")]
        result = _row_to_dict(row)
        checklist = await p.fetch(
            "SELECT id, text, is_checked, position FROM checklist_items "
            "WHERE task_id = $1::uuid ORDER BY position",
            arguments["task_id"],
        )
        result["checklist_items"] = [_row_to_dict(c) for c in checklist]
        tags = await p.fetch(
            "SELECT tg.id, tg.name, tg.color FROM tags tg "
            "JOIN task_tags tt ON tt.tag_id = tg.id WHERE tt.task_id = $1::uuid",
            arguments["task_id"],
        )
        result["tags"] = [_row_to_dict(t) for t in tags]
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "create_task":
        row = await p.fetchrow(
            "INSERT INTO tasks (title, project_id, board_column_id, description, assignee, "
            "pipeline_column_id, due_date, recurrence_rule, board_position) "
            "VALUES ($1, $2::uuid, $3::uuid, $4, $5, $6::uuid, $7::date, $8, "
            "(SELECT COALESCE(MAX(board_position), 0) + 1 FROM tasks WHERE board_column_id = $3::uuid)) "
            "RETURNING id, title",
            arguments["title"],
            arguments["project_id"],
            arguments["board_column_id"],
            arguments.get("description"),
            arguments.get("assignee", "me"),
            arguments.get("pipeline_column_id"),
            arguments.get("due_date"),
            arguments.get("recurrence_rule"),
        )
        return [TextContent(type="text", text=json.dumps(_row_to_dict(row), indent=2))]

    elif name == "update_task":
        task_id = arguments.pop("task_id")
        sets = []
        params = []
        idx = 1
        for key in ("title", "description", "assignee", "is_completed", "recurrence_rule"):
            if key in arguments:
                sets.append(f"{key} = ${idx}")
                params.append(arguments[key])
                idx += 1
        if "due_date" in arguments:
            sets.append(f"due_date = ${idx}::date")
            params.append(arguments["due_date"])
            idx += 1
        if not sets:
            return [TextContent(type="text", text="Keine Felder zum Aktualisieren")]
        params.append(task_id)
        row = await p.fetchrow(
            f"UPDATE tasks SET {', '.join(sets)}, updated_at = now() WHERE id = ${idx}::uuid RETURNING id, title, assignee, is_completed",
            *params,
        )
        return [TextContent(type="text", text=json.dumps(_row_to_dict(row), indent=2))]

    elif name == "get_agent_job":
        row = await p.fetchrow(
            "SELECT aj.*, t.title as task_title FROM agent_jobs aj "
            "JOIN tasks t ON t.id = aj.task_id WHERE aj.id = $1::uuid",
            arguments["job_id"],
        )
        if row is None:
            return [TextContent(type="text", text="Job nicht gefunden")]
        return [TextContent(type="text", text=json.dumps(_row_to_dict(row), indent=2))]

    elif name == "list_agent_jobs":
        status_filter = arguments.get("status")
        if status_filter:
            rows = await p.fetch(
                "SELECT aj.id, aj.task_id, aj.status, aj.created_at, t.title as task_title "
                "FROM agent_jobs aj JOIN tasks t ON t.id = aj.task_id "
                "WHERE aj.status = $1 ORDER BY aj.created_at DESC",
                status_filter,
            )
        else:
            rows = await p.fetch(
                "SELECT aj.id, aj.task_id, aj.status, aj.created_at, t.title as task_title "
                "FROM agent_jobs aj JOIN tasks t ON t.id = aj.task_id "
                "ORDER BY aj.created_at DESC LIMIT 20"
            )
        return [TextContent(type="text", text=json.dumps([_row_to_dict(r) for r in rows], indent=2))]

    elif name == "update_agent_job":
        job_id = arguments.pop("job_id")
        sets = []
        params = []
        idx = 1
        for key in ("status", "output", "error_message", "llm_model", "tokens_used", "cost_usd"):
            if key in arguments:
                sets.append(f"{key} = ${idx}")
                params.append(arguments[key])
                idx += 1

        if not sets:
            return [TextContent(type="text", text="Keine Felder zum Aktualisieren")]

        status_val = arguments.get("status")
        if status_val == "running":
            sets.append(f"started_at = ${idx}")
            params.append(datetime.now(timezone.utc))
            idx += 1
        if status_val in ("completed", "failed"):
            sets.append(f"completed_at = ${idx}")
            params.append(datetime.now(timezone.utc))
            idx += 1

        params.append(job_id)
        row = await p.fetchrow(
            f"UPDATE agent_jobs SET {', '.join(sets)} WHERE id = ${idx}::uuid RETURNING id, status, output",
            *params,
        )
        return [TextContent(type="text", text=json.dumps(_row_to_dict(row), indent=2))]

    elif name == "get_sender_profile":
        email = arguments["email"].lower().strip()
        row = await p.fetchrow(
            "SELECT * FROM sender_profiles WHERE email = $1", email
        )
        if row is None:
            return [TextContent(type="text", text=json.dumps({
                "email": email,
                "exists": False,
                "display_name": None,
                "organization": None,
                "relationship": "unbekannt",
                "tone": "neutral",
                "language": "de",
                "notes": None,
                "email_count": 0,
                "last_contact_at": None,
            }, indent=2, ensure_ascii=False))]
        result = _row_to_dict(row)
        result["exists"] = True
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

    elif name == "update_sender_profile":
        email = arguments["email"].lower().strip()
        row = await p.fetchrow(
            "SELECT id FROM sender_profiles WHERE email = $1", email
        )
        if row is None:
            new_row = await p.fetchrow(
                "INSERT INTO sender_profiles (email, display_name, organization, relationship, tone, language, notes, email_count, last_contact_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, 1, now()) RETURNING *",
                email,
                arguments.get("display_name"),
                arguments.get("organization"),
                arguments.get("relationship", "unbekannt"),
                arguments.get("tone", "neutral"),
                arguments.get("language", "de"),
                arguments.get("notes"),
            )
            result = _row_to_dict(new_row)
            result["action"] = "created"
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
        else:
            sets = ["email_count = email_count + 1", "last_contact_at = now()"]
            params = []
            idx = 1
            for key in ("display_name", "organization", "relationship", "tone", "language", "notes"):
                if key in arguments:
                    sets.append(f"{key} = ${idx}")
                    params.append(arguments[key])
                    idx += 1
            params.append(email)
            updated = await p.fetchrow(
                f"UPDATE sender_profiles SET {', '.join(sets)} WHERE email = ${idx} RETURNING *",
                *params,
            )
            result = _row_to_dict(updated)
            result["action"] = "updated"
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

    elif name == "web_search":
        query = arguments.get("query", "").strip()
        if not query:
            return [TextContent(type="text", text="Suchbegriff fehlt")]

        tavily_key = _env("TP_TAVILY_API_KEY")
        if not tavily_key:
            return [TextContent(type="text", text="Tavily API-Key nicht konfiguriert (TP_TAVILY_API_KEY)")]

        search_depth = arguments.get("search_depth", "basic")
        max_results = min(arguments.get("max_results", 5), 10)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "search_depth": search_depth,
                    "include_answer": True,
                    "include_raw_content": False,
                    "max_results": max_results,
                },
            )
            if resp.status_code != 200:
                return [TextContent(type="text", text=f"Tavily-Fehler: {resp.status_code} {resp.text}")]
            data = resp.json()

        results = data.get("results", [])
        answer = data.get("answer")

        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score"),
            })

        credits = 2 if search_depth == "advanced" else 1
        task_id = arguments.get("task_id")

        await p.execute(
            "INSERT INTO web_searches (query, provider, results, result_count, triggered_by, task_id, credits_used) "
            "VALUES ($1, 'tavily', $2::jsonb, $3, 'agent', $4::uuid, $5)",
            query, json.dumps(formatted), len(formatted), task_id, credits,
        )

        output = {"query": query, "answer": answer, "results": formatted, "credits_used": credits}
        return [TextContent(type="text", text=json.dumps(output, indent=2, ensure_ascii=False))]

    return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

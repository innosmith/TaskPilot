"""TaskPilot MCP-Server — nanobot kann Tasks und Agent-Jobs lesen/schreiben."""

import asyncio
import json
import os
from datetime import datetime, timezone

import asyncpg
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


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
            "INSERT INTO tasks (title, project_id, board_column_id, description, assignee, pipeline_column_id, board_position) "
            "VALUES ($1, $2::uuid, $3::uuid, $4, $5, $6::uuid, "
            "(SELECT COALESCE(MAX(board_position), 0) + 1 FROM tasks WHERE board_column_id = $3::uuid)) "
            "RETURNING id, title",
            arguments["title"],
            arguments["project_id"],
            arguments["board_column_id"],
            arguments.get("description"),
            arguments.get("assignee", "me"),
            arguments.get("pipeline_column_id"),
        )
        return [TextContent(type="text", text=json.dumps(_row_to_dict(row), indent=2))]

    elif name == "update_task":
        task_id = arguments.pop("task_id")
        sets = []
        params = []
        idx = 1
        for key in ("title", "description", "assignee", "is_completed"):
            if key in arguments:
                sets.append(f"{key} = ${idx}")
                params.append(arguments[key])
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

    return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

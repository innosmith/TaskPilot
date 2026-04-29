"""MCP-Server für SIGNA Strategic Intelligence.

Nanobot kann diesen Server nutzen, um Signale zu recherchieren,
Briefings zu lesen und Deep-Dive-Berichte abzurufen.
Read-only-Zugriff auf die SIGNA PostgreSQL-Datenbank.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime
from decimal import Decimal

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "signa"))
from signa_client import SignaClient, SignaConfig  # noqa: E402

logger = logging.getLogger("mcp_signa")

TOOLS = [
    Tool(
        name="search_signals",
        description="SIGNA-Signale durchsuchen. Findet RSS-Artikel, YouTube-Transkripte und Web-Inhalte nach Suchbegriff, Mindest-Score, Typ, Topic oder Persona.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff (durchsucht Titel, Beschreibung, Volltext)"},
                "min_score": {"type": "number", "description": "Mindest-Score (0-10, Standard 6)"},
                "type": {"type": "string", "enum": ["rss", "youtube", "web"], "description": "Signal-Typ filtern"},
                "topic": {"type": "string", "description": "Topic-Name filtern"},
                "persona": {"type": "string", "description": "Persona/Rolle filtern"},
                "since": {"type": "string", "description": "Nur Signale seit diesem Datum (ISO-Format, z.B. 2026-04-01)"},
                "limit": {"type": "integer", "description": "Max. Ergebnisse (Standard 20)"},
            },
        },
    ),
    Tool(
        name="get_signal",
        description="Einzelnes SIGNA-Signal mit vollem Inhalt abrufen (Artikel-Text, YouTube-Transkript etc.).",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Signal-ID"},
            },
            "required": ["id"],
        },
    ),
    Tool(
        name="list_briefings",
        description="Tägliche SIGNA-Briefings auflisten (Zusammenfassungen der wichtigsten Signale).",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max. Ergebnisse (Standard 10)"},
            },
        },
    ),
    Tool(
        name="get_briefing",
        description="Einzelnes Tages-Briefing mit vollständigem HTML-Inhalt und Podcast-Info abrufen.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Briefing-ID"},
            },
            "required": ["id"],
        },
    ),
    Tool(
        name="list_deep_dives",
        description="SIGNA Deep-Dive-Synthesen auflisten (tiefgreifende Analysen pro Persona).",
        inputSchema={
            "type": "object",
            "properties": {
                "persona": {"type": "string", "description": "Nach Persona filtern (optional)"},
                "limit": {"type": "integer", "description": "Max. Ergebnisse (Standard 10)"},
            },
        },
    ),
    Tool(
        name="get_deep_dive",
        description="Einzelne Deep-Dive-Synthese mit vollständigem Bericht abrufen.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Deep-Dive-ID"},
            },
            "required": ["id"],
        },
    ),
    Tool(
        name="get_personas",
        description="Alle SIGNA-Personas (Rollen) auflisten mit Beschreibung.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_topics",
        description="Alle SIGNA-Topics (Themen) mit Gewichtung und Kategorie auflisten.",
        inputSchema={"type": "object", "properties": {}},
    ),
]


def _json_serial(obj):
    """JSON-Serializer für Typen, die asyncpg zurückgibt."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def _to_json(data) -> str:
    return json.dumps(data, default=_json_serial, ensure_ascii=False, indent=2)


server = Server("signa")
_client: SignaClient | None = None


def _get_client() -> SignaClient:
    global _client
    if _client is None:
        _client = SignaClient()
    return _client


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        client = _get_client()

        if name == "search_signals":
            query = arguments.get("query", "")
            min_score = arguments.get("min_score", 6)
            limit = arguments.get("limit", 20)
            type_filter = arguments.get("type")
            topic = arguments.get("topic")
            persona = arguments.get("persona")
            since = arguments.get("since")

            if query:
                results = await client.search_signals(query, min_score, limit)
            else:
                results = await client.list_signals(
                    limit=limit, min_score=min_score, type_filter=type_filter,
                    topic=topic, persona=persona, since=since,
                )
            return [TextContent(type="text", text=_to_json(results))]

        elif name == "get_signal":
            result = await client.get_signal(arguments["id"])
            if result is None:
                return [TextContent(type="text", text='{"error": "Signal nicht gefunden"}')]
            return [TextContent(type="text", text=_to_json(result))]

        elif name == "list_briefings":
            results = await client.list_briefings(arguments.get("limit", 10))
            return [TextContent(type="text", text=_to_json(results))]

        elif name == "get_briefing":
            result = await client.get_briefing(arguments["id"])
            if result is None:
                return [TextContent(type="text", text='{"error": "Briefing nicht gefunden"}')]
            return [TextContent(type="text", text=_to_json(result))]

        elif name == "list_deep_dives":
            results = await client.list_deep_dives(
                persona=arguments.get("persona"), limit=arguments.get("limit", 10)
            )
            return [TextContent(type="text", text=_to_json(results))]

        elif name == "get_deep_dive":
            result = await client.get_deep_dive(arguments["id"])
            if result is None:
                return [TextContent(type="text", text='{"error": "Deep Dive nicht gefunden"}')]
            return [TextContent(type="text", text=_to_json(result))]

        elif name == "get_personas":
            results = await client.list_personas()
            return [TextContent(type="text", text=_to_json(results))]

        elif name == "get_topics":
            results = await client.list_topics()
            return [TextContent(type="text", text=_to_json(results))]

        else:
            return [TextContent(type="text", text=f'{{"error": "Unbekanntes Tool: {name}"}}')]

    except Exception as exc:
        logger.exception("MCP-Tool %s fehlgeschlagen", name)
        return [TextContent(type="text", text=f'{{"error": "{exc!s}"}}')]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

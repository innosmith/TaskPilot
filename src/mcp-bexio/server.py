"""MCP-Server für Bexio Buchhaltung.

Nanobot kann diesen Server als Tool nutzen, um Kontakte, Aufträge,
Rechnungen und Projekte in Bexio zu lesen und anzulegen.
"""

import asyncio
import json
import logging
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bexio"))
from bexio_client import BexioClient, BexioConfig  # noqa: E402

logger = logging.getLogger("mcp_bexio")

TOOLS = [
    Tool(
        name="test_connection",
        description="Bexio Verbindung testen und aktiven Benutzer anzeigen.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="list_contacts",
        description="Kontakte in Bexio auflisten (Kunden, Lieferanten).",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 50},
                "offset": {"type": "integer", "default": 0},
            },
        },
    ),
    Tool(
        name="get_contact",
        description="Details eines Bexio-Kontakts laden (Adresse, E-Mail, Typ).",
        inputSchema={
            "type": "object",
            "properties": {"contact_id": {"type": "integer"}},
            "required": ["contact_id"],
        },
    ),
    Tool(
        name="search_contact",
        description="Bexio-Kontakt nach Name oder E-Mail suchen.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name zum Suchen"},
                "email": {"type": "string", "description": "E-Mail zum Suchen (alternativ zu Name)"},
            },
        },
    ),
    Tool(
        name="create_contact",
        description="Neuen Kontakt in Bexio anlegen.",
        inputSchema={
            "type": "object",
            "properties": {
                "name_1": {"type": "string", "description": "Firmenname oder Nachname"},
                "name_2": {"type": "string", "description": "Vorname (optional)"},
                "contact_type_id": {"type": "integer", "description": "1=Firma, 2=Person", "default": 1},
                "mail": {"type": "string", "description": "E-Mail-Adresse"},
                "address": {"type": "string"},
                "postcode": {"type": "string"},
                "city": {"type": "string"},
                "country_id": {"type": "integer", "description": "Land-ID (1=Schweiz)", "default": 1},
            },
            "required": ["name_1", "contact_type_id"],
        },
    ),
    Tool(
        name="list_orders",
        description="Aufträge (kb_order) in Bexio auflisten. Optional nach Kontakt filtern.",
        inputSchema={
            "type": "object",
            "properties": {
                "contact_id": {"type": "integer", "description": "Kontakt-ID zum Filtern"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    ),
    Tool(
        name="get_order",
        description="Details eines Bexio-Auftrags laden.",
        inputSchema={
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"],
        },
    ),
    Tool(
        name="list_projects",
        description="Projekte in Bexio auflisten.",
        inputSchema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 50}},
        },
    ),
    Tool(
        name="get_project",
        description="Details eines Bexio-Projekts laden.",
        inputSchema={
            "type": "object",
            "properties": {"project_id": {"type": "integer"}},
            "required": ["project_id"],
        },
    ),
]

server = Server("taskpilot-bexio")
_client: BexioClient | None = None


def _get_client() -> BexioClient:
    global _client
    if _client is None:
        _client = BexioClient(BexioConfig.from_env())
    return _client


def _json_response(data) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str, ensure_ascii=False))]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    c = _get_client()

    if name == "test_connection":
        result = await c.test_connection()
        return _json_response(result)

    if name == "list_contacts":
        result = await c.list_contacts(
            limit=arguments.get("limit", 50),
            offset=arguments.get("offset", 0),
        )
        compact = [
            {"id": ct.get("id"), "name_1": ct.get("name_1"), "name_2": ct.get("name_2"),
             "mail": ct.get("mail"), "contact_type_id": ct.get("contact_type_id")}
            for ct in result
        ]
        return _json_response(compact)

    if name == "get_contact":
        result = await c.get_contact(arguments["contact_id"])
        return _json_response(result)

    if name == "search_contact":
        if arguments.get("email"):
            result = await c.search_contact_by_email(arguments["email"])
        elif arguments.get("name"):
            result = await c.search_contact_by_name(arguments["name"])
        else:
            return _json_response({"error": "name oder email erforderlich"})
        compact = [
            {"id": ct.get("id"), "name_1": ct.get("name_1"), "name_2": ct.get("name_2"),
             "mail": ct.get("mail")}
            for ct in result
        ]
        return _json_response(compact)

    if name == "create_contact":
        result = await c.create_contact(arguments)
        return _json_response(result)

    if name == "list_orders":
        result = await c.list_orders(
            contact_id=arguments.get("contact_id"),
            limit=arguments.get("limit", 50),
        )
        compact = [
            {"id": o.get("id"), "title": o.get("title"), "contact_id": o.get("contact_id"),
             "total": o.get("total"), "status": o.get("kb_item_status_id")}
            for o in result
        ]
        return _json_response(compact)

    if name == "get_order":
        result = await c.get_order(arguments["order_id"])
        return _json_response(result)

    if name == "list_projects":
        result = await c.list_projects(limit=arguments.get("limit", 50))
        compact = [
            {"id": p.get("id"), "name": p.get("name"), "contact_id": p.get("contact_id"),
             "status_id": p.get("pr_state_id")}
            for p in result
        ]
        return _json_response(compact)

    if name == "get_project":
        result = await c.get_project(arguments["project_id"])
        return _json_response(result)

    return _json_response({"error": f"Unbekanntes Tool: {name}"})


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

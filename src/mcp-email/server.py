"""MCP-Server für E-Mail-Zugriff via Microsoft Graph API.

nanobot kann diesen Server als Tool nutzen, um E-Mails zu lesen,
Entwürfe zu erstellen und (nach Approval) zu versenden.
"""

import asyncio
import json
import logging
import os
import re
import sys
import time

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "email-graph"))
from graph_client import GraphClient, GraphConfig  # noqa: E402

logger = logging.getLogger("mcp_email")


def _html_to_text(html: str) -> str:
    """HTML in lesbaren Plain-Text konvertieren."""
    if not html:
        return ""
    text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

TOOLS = [
    Tool(
        name="list_email_folders",
        description="Alle verfügbaren E-Mail-Ordner auflisten",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="list_emails",
        description="E-Mails aus einem Ordner lesen (Standard: Posteingang)",
        inputSchema={
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "default": "inbox",
                    "description": "Ordner-Name oder ID (inbox, drafts, sentitems, etc.)",
                },
                "top": {"type": "integer", "default": 10},
                "skip": {"type": "integer", "default": 0},
                "filter": {
                    "type": "string",
                    "description": "OData-Filter, z.B. \"isRead eq false\"",
                },
            },
        },
    ),
    Tool(
        name="get_email",
        description="Eine einzelne E-Mail mit vollem Body laden",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Graph-API Message-ID"},
            },
            "required": ["message_id"],
        },
    ),
    Tool(
        name="get_email_categories",
        description="CoPilot-Kategorien und Klassifizierung einer E-Mail lesen",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
            },
            "required": ["message_id"],
        },
    ),
    Tool(
        name="create_draft",
        description="E-Mail-Entwurf im Drafts-Ordner erstellen. HITL: Entwurf muss vor Versand genehmigt werden.",
        inputSchema={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "body_html": {"type": "string", "description": "HTML-Body der E-Mail"},
                "to_recipients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste von E-Mail-Adressen",
                },
                "cc_recipients": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "reply_to_id": {
                    "type": "string",
                    "description": "Message-ID der Original-Mail (für Antworten)",
                },
            },
            "required": ["subject", "body_html", "to_recipients"],
        },
    ),
    Tool(
        name="send_email",
        description="Einen bestehenden Entwurf versenden. ACHTUNG: Erfordert vorherige Genehmigung (HITL L1)!",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "ID des zu sendenden Entwurfs"},
            },
            "required": ["message_id"],
        },
    ),
    Tool(
        name="mark_as_read",
        description="E-Mail als gelesen markieren",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
            },
            "required": ["message_id"],
        },
    ),
    # ── Kalender-Tools ──────────────────────────────────────────
    Tool(
        name="list_calendar_events",
        description="Kalendertermine in einem Zeitraum abrufen",
        inputSchema={
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start-Zeitpunkt ISO 8601 (z.B. 2026-04-27T00:00:00)"},
                "end": {"type": "string", "description": "End-Zeitpunkt ISO 8601 (z.B. 2026-04-27T23:59:59)"},
                "top": {"type": "integer", "default": 20},
            },
            "required": ["start", "end"],
        },
    ),
    Tool(
        name="get_calendar_event",
        description="Einzelnen Kalendertermin laden",
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
            },
            "required": ["event_id"],
        },
    ),
    Tool(
        name="create_calendar_event",
        description="Termin oder Zeitblocker im Kalender erstellen. Eigene Zeitblocker: L2 (Agent erstellt). Termine mit anderen: L1 (Approval nötig).",
        inputSchema={
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Titel des Termins"},
                "start": {"type": "string", "description": "Start ISO 8601 (z.B. 2026-04-28T14:00:00)"},
                "end": {"type": "string", "description": "Ende ISO 8601 (z.B. 2026-04-28T16:00:00)"},
                "body": {"type": "string", "description": "Optionale Beschreibung (HTML)"},
                "location": {"type": "string", "description": "Ort (optional)"},
                "show_as": {"type": "string", "enum": ["free", "tentative", "busy", "oof"], "default": "busy"},
            },
            "required": ["subject", "start", "end"],
        },
    ),
    Tool(
        name="find_free_slots",
        description="Freie Zeitfenster im Kalender finden für einen bestimmten Zeitraum",
        inputSchema={
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start ISO 8601"},
                "end": {"type": "string", "description": "Ende ISO 8601"},
                "duration_minutes": {"type": "integer", "default": 60, "description": "Gewünschte Dauer in Minuten"},
            },
            "required": ["start", "end"],
        },
    ),
    # ── Outlook-Kategorie & Ordner-Tools ─────────────────────
    Tool(
        name="get_thread",
        description="Alle Nachrichten eines E-Mail-Threads (Konversation) chronologisch laden. Gibt den gesamten Verlauf zurueck.",
        inputSchema={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "conversationId der E-Mail (aus get_email)"},
                "top": {"type": "integer", "default": 10, "description": "Max. Anzahl Nachrichten"},
            },
            "required": ["conversation_id"],
        },
    ),
    Tool(
        name="search_sender_history",
        description="Letzte E-Mails eines bestimmten Absenders abrufen (neueste zuerst). Nuetzlich fuer Kontext ueber die bisherige Kommunikation.",
        inputSchema={
            "type": "object",
            "properties": {
                "sender_email": {"type": "string", "description": "E-Mail-Adresse des Absenders"},
                "top": {"type": "integer", "default": 5, "description": "Max. Anzahl E-Mails"},
            },
            "required": ["sender_email"],
        },
    ),
    Tool(
        name="search_emails",
        description="Volltextsuche ueber alle E-Mails. Findet relevante Nachrichten zu einem Thema.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff(e)"},
                "top": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    ),
    # ── Outlook-Kategorie & Ordner-Tools (original) ──────────
    Tool(
        name="set_email_categories",
        description="Outlook-Kategorien auf einer E-Mail setzen (z.B. 'Wichtig', 'Newsletter'). Ersetzt bestehende Kategorien.",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Graph-API Message-ID"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste von Kategorienamen (z.B. ['Wichtig'] oder ['Newsletter'])",
                },
            },
            "required": ["message_id", "categories"],
        },
    ),
    Tool(
        name="move_email_to_folder",
        description="E-Mail in einen bestehenden Inbox-Subfolder verschieben. NUR diese Ordner sind erlaubt: System, Newsletter, Junk, Kalender. KEINE neuen Ordner erstellen.",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Graph-API Message-ID"},
                "folder_name": {"type": "string", "enum": ["System", "Newsletter", "Junk", "Kalender"], "description": "Ziel-Ordnername (nur System, Newsletter, Junk oder Kalender)"},
            },
            "required": ["message_id", "folder_name"],
        },
    ),
]


server = Server("taskpilot-email")
_client: GraphClient | None = None


def _get_client() -> GraphClient:
    global _client
    if _client is None:
        config = GraphConfig.from_env()
        if not config.is_configured:
            raise RuntimeError(
                "Graph API nicht konfiguriert. Setze GRAPH_TENANT_ID, "
                "GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_USER_EMAIL."
            )
        _client = GraphClient(config)
    return _client


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    t0 = time.monotonic()
    logger.info("Tool %s aufgerufen: %s", name, {k: str(v)[:100] for k, v in arguments.items()})
    try:
        client = _get_client()
    except RuntimeError as e:
        logger.error("Client-Fehler: %s", e)
        return [TextContent(type="text", text=str(e))]

    try:
        if name == "list_email_folders":
            folders = await client.list_folders()
            result = [
                {"id": f.get("id", ""), "displayName": f.get("displayName", ""), "totalItemCount": f.get("totalItemCount", 0)}
                for f in folders
            ]
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

        elif name == "list_emails":
            data = await client.list_emails(
                folder=arguments.get("folder", "inbox"),
                top=arguments.get("top", 10),
                skip=arguments.get("skip", 0),
                filter_str=arguments.get("filter"),
            )
            emails = []
            for msg in data.get("value", []):
                emails.append({
                    "id": msg.get("id"),
                    "subject": msg.get("subject"),
                    "from": msg.get("from", {}).get("emailAddress", {}).get("address"),
                    "receivedDateTime": msg.get("receivedDateTime"),
                    "isRead": msg.get("isRead"),
                    "bodyPreview": msg.get("bodyPreview", "")[:200],
                    "categories": msg.get("categories", []),
                    "inferenceClassification": msg.get("inferenceClassification"),
                    "importance": msg.get("importance"),
                    "hasAttachments": msg.get("hasAttachments"),
                })
            return [TextContent(type="text", text=json.dumps(emails, indent=2, ensure_ascii=False))]

        elif name == "get_email":
            msg = await client.get_email(arguments["message_id"])
            return [TextContent(type="text", text=json.dumps(msg, indent=2, ensure_ascii=False))]

        elif name == "get_email_categories":
            cats = await client.get_email_categories(arguments["message_id"])
            return [TextContent(type="text", text=json.dumps(cats, indent=2, ensure_ascii=False))]

        elif name == "create_draft":
            draft = await client.create_draft(
                subject=arguments["subject"],
                body_html=arguments["body_html"],
                to_recipients=arguments["to_recipients"],
                cc_recipients=arguments.get("cc_recipients"),
                reply_to_id=arguments.get("reply_to_id"),
            )
            return [TextContent(
                type="text",
                text=json.dumps({
                    "id": draft.get("id"),
                    "subject": draft.get("subject"),
                    "status": "draft_created",
                    "approval_required": True,
                    "hinweis": "Entwurf muss vor Versand durch den Berater genehmigt werden.",
                }, indent=2, ensure_ascii=False),
            )]

        elif name == "send_email":
            await client.send_draft(arguments["message_id"])
            return [TextContent(type="text", text=json.dumps({
                "status": "sent",
                "message_id": arguments["message_id"],
            }, indent=2))]

        elif name == "mark_as_read":
            await client.mark_as_read(arguments["message_id"])
            return [TextContent(type="text", text=json.dumps({
                "status": "marked_as_read",
                "message_id": arguments["message_id"],
            }, indent=2))]

        elif name == "list_calendar_events":
            events = await client.list_events(
                start=arguments["start"],
                end=arguments["end"],
                top=arguments.get("top", 20),
            )
            result = []
            for ev in events:
                result.append({
                    "id": ev.get("id"),
                    "subject": ev.get("subject"),
                    "start": ev.get("start", {}).get("dateTime"),
                    "end": ev.get("end", {}).get("dateTime"),
                    "isAllDay": ev.get("isAllDay"),
                    "showAs": ev.get("showAs"),
                    "location": (ev.get("location") or {}).get("displayName"),
                    "bodyPreview": ev.get("bodyPreview", "")[:200],
                })
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

        elif name == "get_calendar_event":
            ev = await client.get_event(arguments["event_id"])
            return [TextContent(type="text", text=json.dumps(ev, indent=2, ensure_ascii=False))]

        elif name == "create_calendar_event":
            ev = await client.create_event(
                subject=arguments["subject"],
                start=arguments["start"],
                end=arguments["end"],
                body=arguments.get("body"),
                location=arguments.get("location"),
                show_as=arguments.get("show_as", "busy"),
            )
            return [TextContent(type="text", text=json.dumps({
                "id": ev.get("id"),
                "subject": ev.get("subject"),
                "start": ev.get("start", {}).get("dateTime"),
                "end": ev.get("end", {}).get("dateTime"),
                "status": "event_created",
            }, indent=2, ensure_ascii=False))]

        elif name == "find_free_slots":
            slots = await client.find_free_slots(
                start=arguments["start"],
                end=arguments["end"],
                duration_minutes=arguments.get("duration_minutes", 60),
            )
            return [TextContent(type="text", text=json.dumps(slots, indent=2, ensure_ascii=False))]

        elif name == "get_thread":
            msgs = await client.get_conversation_messages(
                conversation_id=arguments["conversation_id"],
                top=arguments.get("top", 10),
            )
            thread = []
            total_chars = 0
            max_total = 15000
            for msg in msgs:
                if total_chars >= max_total:
                    break
                sender = msg.get("from", {}).get("emailAddress", {})
                body_html = msg.get("body", {}).get("content", "")
                body_text = _html_to_text(body_html)[:3000]
                total_chars += len(body_text)
                thread.append({
                    "id": msg.get("id"),
                    "from": sender.get("address"),
                    "from_name": sender.get("name"),
                    "subject": msg.get("subject"),
                    "receivedDateTime": msg.get("receivedDateTime"),
                    "body_text": body_text,
                })
            logger.info("get_thread: %d Nachrichten, %d Zeichen Kontext", len(thread), total_chars)
            result_text = json.dumps(thread, indent=2, ensure_ascii=False)
            return [TextContent(type="text", text=result_text)]

        elif name == "search_sender_history":
            msgs = await client.search_sender_emails(
                sender_email=arguments["sender_email"],
                top=arguments.get("top", 5),
            )
            history = []
            for msg in msgs:
                sender = msg.get("from", {}).get("emailAddress", {})
                body_html = msg.get("body", {}).get("content", "")
                body_text = _html_to_text(body_html)[:1500]
                history.append({
                    "id": msg.get("id"),
                    "from": sender.get("address"),
                    "from_name": sender.get("name"),
                    "subject": msg.get("subject"),
                    "receivedDateTime": msg.get("receivedDateTime"),
                    "body_text": body_text,
                    "conversationId": msg.get("conversationId"),
                })
            logger.info("search_sender_history(%s): %d Ergebnisse", arguments["sender_email"], len(history))
            result_text = json.dumps(history, indent=2, ensure_ascii=False)
            return [TextContent(type="text", text=result_text)]

        elif name == "search_emails":
            msgs = await client.search_emails(
                query=arguments["query"],
                top=arguments.get("top", 5),
            )
            results = []
            for msg in msgs:
                sender = msg.get("from", {}).get("emailAddress", {})
                results.append({
                    "id": msg.get("id"),
                    "from": sender.get("address"),
                    "subject": msg.get("subject"),
                    "receivedDateTime": msg.get("receivedDateTime"),
                    "bodyPreview": msg.get("bodyPreview", "")[:300],
                })
            return [TextContent(type="text", text=json.dumps(results, indent=2, ensure_ascii=False))]

        elif name == "set_email_categories":
            result = await client.set_categories(
                message_id=arguments["message_id"],
                categories=arguments["categories"],
            )
            return [TextContent(type="text", text=json.dumps({
                "status": "categories_set",
                "message_id": arguments["message_id"],
                "categories": arguments["categories"],
            }, indent=2, ensure_ascii=False))]

        elif name == "move_email_to_folder":
            allowed = {"System", "Newsletter", "Junk", "Kalender"}
            folder = arguments["folder_name"]
            if folder not in allowed:
                return [TextContent(type="text", text=json.dumps({
                    "status": "error",
                    "message": f"Ordner '{folder}' nicht erlaubt. Nur: {', '.join(sorted(allowed))}",
                }, indent=2, ensure_ascii=False))]
            result = await client.move_to_folder(
                message_id=arguments["message_id"],
                folder_name=folder,
            )
            return [TextContent(type="text", text=json.dumps({
                "status": "moved",
                "message_id": arguments["message_id"],
                "folder": arguments["folder_name"],
                "new_id": result.get("id"),
            }, indent=2, ensure_ascii=False))]

        return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]

    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        logger.error("Tool %s fehlgeschlagen nach %.0fms: %s: %s", name, elapsed, type(e).__name__, e)
        return [TextContent(type="text", text=f"Fehler: {type(e).__name__}: {e}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

"""MCP-Client-Service für contentConverter.

Startet den contentConverter MCP-Server als Singleton-Subprocess (stdio)
und stellt eine async API für die Backend-Router bereit.

Der Prozess wird beim Backend-Start (Lifespan) gestartet und beim
Shutdown sauber beendet. Bei Absturz wird automatisch reconnected.
"""

import asyncio
import logging
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import get_settings

logger = logging.getLogger("taskpilot.content_converter")

_session: ClientSession | None = None
_exit_stack: AsyncExitStack | None = None
_lock = asyncio.Lock()


async def start_content_converter() -> None:
    """Startet den contentConverter MCP-Server als Singleton-Subprocess."""
    global _session, _exit_stack

    settings = get_settings()
    cconv_bin = settings.contentconverter_cconv_bin

    if not Path(cconv_bin).exists():
        logger.warning(
            "cconv Binary nicht gefunden: %s -- contentConverter deaktiviert", cconv_bin
        )
        return

    try:
        _exit_stack = AsyncExitStack()

        server_params = StdioServerParameters(
            command=cconv_bin,
            args=["serve"],
        )

        stdio_transport = await _exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = stdio_transport

        _session = await _exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await _session.initialize()

        tools = await _session.list_tools()
        tool_names = [t.name for t in tools.tools]
        logger.info(
            "contentConverter MCP-Server gestartet -- %d Tools: %s",
            len(tool_names),
            ", ".join(tool_names),
        )
    except Exception:
        logger.exception("contentConverter MCP-Server konnte nicht gestartet werden")
        _session = None
        if _exit_stack:
            await _exit_stack.aclose()
            _exit_stack = None


async def stop_content_converter() -> None:
    """Beendet den contentConverter MCP-Server."""
    global _session, _exit_stack

    if _exit_stack:
        try:
            await _exit_stack.aclose()
        except Exception:
            logger.exception("Fehler beim Beenden des contentConverter MCP-Servers")
        _exit_stack = None
    _session = None
    logger.info("contentConverter MCP-Server beendet")


async def _ensure_session() -> ClientSession:
    """Stellt sicher, dass eine aktive Session existiert (Reconnect bei Bedarf)."""
    global _session
    if _session is None:
        async with _lock:
            if _session is None:
                logger.info("contentConverter MCP-Session verloren -- Reconnect...")
                await start_content_converter()
            if _session is None:
                raise RuntimeError("contentConverter MCP-Server nicht verfügbar")
    return _session


async def call_tool(tool_name: str, **kwargs) -> dict | str | list:
    """Ruft ein MCP-Tool auf dem contentConverter-Server auf.

    Args:
        tool_name: Name des MCP-Tools (z.B. "convert_to_word", "anonymize_content")
        **kwargs: Tool-Parameter

    Returns:
        Tool-Ergebnis (Text oder strukturierte Daten)

    Raises:
        RuntimeError: Wenn der MCP-Server nicht verfügbar ist
    """
    session = await _ensure_session()

    try:
        result = await session.call_tool(tool_name, arguments=kwargs)

        if result.content and len(result.content) == 1:
            content = result.content[0]
            if hasattr(content, "text"):
                text = content.text
                try:
                    import json
                    return json.loads(text)
                except (json.JSONDecodeError, ValueError):
                    return text

        return [
            c.text if hasattr(c, "text") else str(c) for c in (result.content or [])
        ]

    except Exception as e:
        global _session
        _session = None
        logger.error("contentConverter MCP-Tool '%s' fehlgeschlagen: %s", tool_name, e)
        raise RuntimeError(f"contentConverter-Fehler: {e}") from e

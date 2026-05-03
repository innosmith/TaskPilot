"""Gemini Deep Research Service — Interactions API Integration.

Nutzt die Google Gemini Interactions API (Public Beta) für autonome
Multi-Step-Recherche mit Streaming-Support.
"""

import logging
import time
from typing import AsyncGenerator

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_MODEL = "deep-research-preview-04-2026"
MAX_MODEL = "deep-research-max-preview-04-2026"


def _get_api_key() -> str:
    settings = get_settings()
    key = settings.gemini_api_key
    if not key:
        raise RuntimeError("TP_GEMINI_API_KEY nicht konfiguriert")
    return key


async def start_research(query: str, model: str | None = None) -> str:
    """Startet eine Gemini Deep Research Aufgabe (non-streaming).

    Returns: interaction_id zum späteren Polling.
    """
    api_key = _get_api_key()
    agent = model or DEFAULT_MODEL

    payload = {
        "input": query,
        "agent": agent,
        "background": True,
        "store": True,
        "agent_config": {
            "type": "deep-research",
            "thinking_summaries": "auto",
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            INTERACTIONS_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
        )
        if resp.status_code not in (200, 201):
            logger.error("Gemini Interactions API Fehler: %d %s", resp.status_code, resp.text)
            raise RuntimeError(f"Gemini API Fehler: {resp.status_code} — {resp.text[:200]}")

        data = resp.json()
        interaction_id = data.get("id")
        if not interaction_id:
            raise RuntimeError("Keine interaction_id in Gemini-Antwort")
        return interaction_id


async def poll_research(interaction_id: str) -> dict:
    """Pollt den Status einer laufenden Recherche.

    Returns: dict mit 'status', 'outputs', 'usage'.
    """
    api_key = _get_api_key()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{INTERACTIONS_URL}/{interaction_id}",
            headers={"x-goog-api-key": api_key},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini Poll-Fehler: {resp.status_code}")
        return resp.json()


async def stream_research(query: str, model: str | None = None) -> AsyncGenerator[dict, None]:
    """Streamt eine Gemini Deep Research Aufgabe via SSE.

    Yields dicts: {"type": "thought"|"text"|"status"|"error"|"done", "content": ...}
    """
    import json

    api_key = _get_api_key()
    agent = model or DEFAULT_MODEL

    payload = {
        "input": query,
        "agent": agent,
        "background": True,
        "stream": True,
        "agent_config": {
            "type": "deep-research",
            "thinking_summaries": "auto",
        },
    }

    interaction_id = None
    event_type = ""
    start_time = time.time()
    last_status_time = start_time

    async with httpx.AsyncClient(timeout=1200.0) as client:
        try:
            async with client.stream(
                "POST",
                f"{INTERACTIONS_URL}?alt=sse",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
            ) as resp:
                if resp.status_code not in (200, 201):
                    body = await resp.aread()
                    logger.error("Gemini Deep Research Stream-Fehler: %d — %s", resp.status_code, body.decode()[:300])
                    raise RuntimeError(f"Gemini Stream-Fehler: {resp.status_code} — {body.decode()[:200]}")

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue

                    if line.startswith("id:"):
                        continue

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        continue

                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue

                        logger.debug("[DeepResearch] event=%s data_keys=%s", event_type, list(data.keys())[:5])

                        if event_type == "interaction.start":
                            interaction_id = data.get("id")
                            yield {"type": "status", "content": "Recherche gestartet..."}

                        elif event_type == "content.delta":
                            delta = data.get("delta", {})
                            delta_type = delta.get("type", "")

                            if delta_type == "thought_summary":
                                text = delta.get("content", {}).get("text", "") if isinstance(delta.get("content"), dict) else delta.get("text", "")
                                if text:
                                    yield {"type": "thought", "content": text}

                                now = time.time()
                                if now - last_status_time > 60:
                                    elapsed_min = int((now - start_time) / 60)
                                    yield {"type": "status", "content": f"Recherche aktiv — Denkphase seit {elapsed_min} Min..."}
                                    last_status_time = now

                            elif delta_type == "text":
                                text = delta.get("text", "")
                                if text:
                                    yield {"type": "text", "content": text}

                        elif event_type == "interaction.complete":
                            outputs = data.get("outputs", [])
                            final_text = ""
                            for out in outputs:
                                if out.get("type") == "text":
                                    final_text += out.get("text", "")
                            elapsed = int(time.time() - start_time)
                            logger.info("Gemini Deep Research abgeschlossen in %ds (interaction=%s)", elapsed, interaction_id)
                            yield {"type": "done", "content": final_text, "interaction_id": interaction_id}
                            return

                        elif event_type == "error":
                            yield {"type": "error", "content": data.get("message", "Unbekannter Fehler")}
                            return

        except httpx.ReadTimeout:
            elapsed = int(time.time() - start_time)
            logger.warning("Gemini Deep Research Timeout nach %ds (interaction=%s)", elapsed, interaction_id)
            if not interaction_id:
                yield {"type": "error", "content": f"Zeitüberschreitung nach {elapsed}s — keine Interaction-ID erhalten"}
                return
            yield {"type": "status", "content": f"Stream-Timeout nach {elapsed}s — Ergebnis wird per Polling abgeholt..."}

    if interaction_id:
        import asyncio
        for attempt in range(120):
            await asyncio.sleep(10)
            try:
                result = await poll_research(interaction_id)
            except Exception as e:
                logger.warning("Polling-Fehler (Versuch %d): %s", attempt, e)
                continue
            status = result.get("status")
            if status == "completed":
                outputs = result.get("outputs", [])
                final_text = ""
                for out in outputs:
                    if out.get("type") == "text":
                        final_text += out.get("text", "")
                yield {"type": "done", "content": final_text, "interaction_id": interaction_id}
                return
            elif status == "failed":
                yield {"type": "error", "content": result.get("error", "Recherche fehlgeschlagen")}
                return
            elif attempt % 6 == 0:
                elapsed = int(time.time() - start_time)
                yield {"type": "status", "content": f"Recherche läuft... ({elapsed}s, Status: {status})"}

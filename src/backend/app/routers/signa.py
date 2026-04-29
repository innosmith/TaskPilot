"""FastAPI Router für SIGNA Strategic Intelligence (Frontend-Zugriff)."""

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.models import User

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "signa"))
from signa_client import SignaClient, SignaConfig  # noqa: E402

router = APIRouter(prefix="/api/signa", tags=["signa"])
logger = logging.getLogger("taskpilot.signa")

_client: SignaClient | None = None


def _get_signa_client() -> SignaClient:
    global _client
    if _client is None:
        cfg = SignaConfig.from_env()
        if not cfg.is_configured:
            raise HTTPException(status_code=400, detail="SIGNA-Datenbank nicht konfiguriert (ISI_* Env-Vars fehlen)")
        _client = SignaClient(cfg)
    return _client


# ── Test ──────────────────────────────────────────────

@router.get("/test-connection")
async def test_connection(user: User = Depends(get_current_user)):
    try:
        client = _get_signa_client()
        return await client.test_connection()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("SIGNA Verbindungstest fehlgeschlagen: %s", e)
        raise HTTPException(status_code=502, detail=f"Verbindung fehlgeschlagen: {e}")


# ── Signals ───────────────────────────────────────────

class SignalSummary(BaseModel):
    id: int
    title: str
    source_name: str | None = None
    url: str | None = None
    type: str | None = None
    status: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    published_at: str | None = None
    total_score: float | None = None
    relevant_role: str | None = None
    ai_reason: str | None = None
    topic_name: str | None = None
    category: str | None = None


class SignalListResponse(BaseModel):
    signals: list[SignalSummary]
    total: int
    limit: int
    offset: int


@router.get("/signals", response_model=SignalListResponse)
async def list_signals(
    limit: int = Query(default=30, le=100),
    offset: int = Query(default=0, ge=0),
    min_score: float | None = None,
    type: str | None = None,
    topic: str | None = None,
    persona: str | None = None,
    since: str | None = None,
    status: str | None = None,
    search: str | None = None,
    user: User = Depends(get_current_user),
):
    client = _get_signa_client()
    signals = await client.list_signals(
        limit=limit, offset=offset, min_score=min_score,
        type_filter=type, topic=topic, persona=persona,
        since=since, status_filter=status, search_term=search,
    )
    total = await client.count_signals(
        min_score=min_score, type_filter=type, topic=topic,
        persona=persona, since=since, status_filter=status, search_term=search,
    )
    return SignalListResponse(
        signals=[SignalSummary(**_serialize(s)) for s in signals],
        total=total, limit=limit, offset=offset,
    )


@router.get("/signals/{signal_id}")
async def get_signal(signal_id: int, user: User = Depends(get_current_user)):
    client = _get_signa_client()
    signal = await client.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal nicht gefunden")
    return _serialize(signal)


# ── Briefings ────────────────────────────────────────

@router.get("/briefings")
async def list_briefings(
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
):
    client = _get_signa_client()
    return await client.list_briefings(limit)


@router.get("/briefings/{briefing_id}")
async def get_briefing(briefing_id: int, user: User = Depends(get_current_user)):
    client = _get_signa_client()
    b = await client.get_briefing(briefing_id)
    if not b:
        raise HTTPException(status_code=404, detail="Briefing nicht gefunden")
    return _serialize(b)


# ── Deep Dives ───────────────────────────────────────

@router.get("/deep-dives")
async def list_deep_dives(
    persona: str | None = None,
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
):
    client = _get_signa_client()
    return await client.list_deep_dives(persona=persona, limit=limit)


@router.get("/deep-dives/{dd_id}")
async def get_deep_dive(dd_id: int, user: User = Depends(get_current_user)):
    client = _get_signa_client()
    dd = await client.get_deep_dive(dd_id)
    if not dd:
        raise HTTPException(status_code=404, detail="Deep Dive nicht gefunden")
    return _serialize(dd)


# ── Stammdaten ───────────────────────────────────────

@router.get("/personas")
async def list_personas(user: User = Depends(get_current_user)):
    client = _get_signa_client()
    return await client.list_personas()


@router.get("/topics")
async def list_topics(user: User = Depends(get_current_user)):
    client = _get_signa_client()
    return await client.list_topics()


# ── Stats ────────────────────────────────────────────

@router.get("/stats")
async def get_stats(user: User = Depends(get_current_user)):
    client = _get_signa_client()
    return await client.get_stats()


# ── Helpers ──────────────────────────────────────────

def _serialize(data: dict) -> dict:
    """asyncpg-Typen (datetime, Decimal) für JSON serialisierbar machen."""
    from datetime import date, datetime
    from decimal import Decimal
    result = {}
    for k, v in data.items():
        if isinstance(v, (datetime, date)):
            result[k] = v.isoformat()
        elif isinstance(v, Decimal):
            result[k] = float(v)
        elif isinstance(v, memoryview):
            result[k] = None
        else:
            result[k] = v
    return result

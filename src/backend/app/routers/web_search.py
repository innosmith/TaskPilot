"""Router für klassische Websuche (Tavily API) mit Historisierung."""

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.models.models import WebSearch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["web-search"])

TAVILY_API_URL = "https://api.tavily.com/search"


async def _tavily_search(query: str, search_depth: str = "basic", max_results: int = 5) -> dict:
    """Tavily-Suche ausführen. basic=1 Credit, advanced=2 Credits."""
    settings = get_settings()
    if not settings.tavily_api_key:
        raise HTTPException(status_code=503, detail="Tavily API-Key nicht konfiguriert")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            TAVILY_API_URL,
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "search_depth": search_depth,
                "include_answer": True,
                "include_raw_content": False,
                "max_results": max_results,
            },
        )
        if resp.status_code != 200:
            logger.error("Tavily-Fehler: %d %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail=f"Tavily-Fehler: {resp.status_code}")
        return resp.json()


@router.post("")
async def perform_search(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Websuche ausführen und historisieren."""
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Suchbegriff fehlt")

    search_depth = body.get("search_depth", "basic")
    max_results = body.get("max_results", 5)
    task_id = body.get("task_id")
    conversation_id = body.get("conversation_id")
    triggered_by = body.get("triggered_by", "user")

    tavily_result = await _tavily_search(query, search_depth, max_results)

    results = tavily_result.get("results", [])
    answer = tavily_result.get("answer")

    formatted_results = []
    for r in results:
        formatted_results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score"),
        })

    credits = 2 if search_depth == "advanced" else 1

    search_record = WebSearch(
        query=query,
        provider="tavily",
        results=formatted_results,
        result_count=len(formatted_results),
        triggered_by=triggered_by,
        task_id=uuid.UUID(task_id) if task_id else None,
        conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
        user_id=user.id,
        credits_used=credits,
    )
    db.add(search_record)
    await db.flush()

    return {
        "id": str(search_record.id),
        "query": query,
        "answer": answer,
        "results": formatted_results,
        "result_count": len(formatted_results),
        "provider": "tavily",
        "credits_used": credits,
        "created_at": search_record.created_at.isoformat(),
    }


@router.get("/history")
async def search_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    task_id: uuid.UUID | None = None,
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Suchverlauf (paginiert, neueste zuerst)."""
    query = select(WebSearch).order_by(WebSearch.created_at.desc())
    count_query = select(func.count()).select_from(WebSearch)

    if task_id:
        query = query.where(WebSearch.task_id == task_id)
        count_query = count_query.where(WebSearch.task_id == task_id)
    if q:
        query = query.where(WebSearch.query.ilike(f"%{q}%"))
        count_query = count_query.where(WebSearch.query.ilike(f"%{q}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    searches = result.scalars().all()

    return {
        "items": [
            {
                "id": str(s.id),
                "query": s.query,
                "provider": s.provider,
                "result_count": s.result_count,
                "triggered_by": s.triggered_by,
                "task_id": str(s.task_id) if s.task_id else None,
                "conversation_id": str(s.conversation_id) if s.conversation_id else None,
                "credits_used": s.credits_used,
                "created_at": s.created_at.isoformat(),
            }
            for s in searches
        ],
        "total": total,
    }


@router.get("/{search_id}")
async def get_search(
    search_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Einzelnes Suchergebnis laden."""
    result = await db.execute(
        select(WebSearch).where(WebSearch.id == search_id)
    )
    search = result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Suchergebnis nicht gefunden")

    return {
        "id": str(search.id),
        "query": search.query,
        "provider": search.provider,
        "results": search.results,
        "result_count": search.result_count,
        "triggered_by": search.triggered_by,
        "task_id": str(search.task_id) if search.task_id else None,
        "conversation_id": str(search.conversation_id) if search.conversation_id else None,
        "user_id": str(search.user_id) if search.user_id else None,
        "credits_used": search.credits_used,
        "created_at": search.created_at.isoformat(),
    }

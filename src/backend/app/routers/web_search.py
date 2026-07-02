"""Router für den Websuche-Verlauf (read-only, Audit).

Die klassische Tavily-Websuche (POST /api/search) wurde entfernt: Die
Hermes-native agentische Recherche (``web_search``/``web_extract`` im
Agent-Modus) ersetzt sie vollständig und wird für den Audit-Trail in
``web_searches`` historisiert (siehe ``routers/chat.py``). Die
Historie-Endpunkte bleiben für Anzeige und Nachvollziehbarkeit erhalten.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_role
from app.database import get_db
from app.models import User
from app.models.models import WebSearch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["web-search"])


@router.get("/history")
async def search_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    task_id: uuid.UUID | None = None,
    q: str | None = None,
    user: User = Depends(require_role("owner")),
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
    user: User = Depends(require_role("owner")),
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

"""Planner-Endpoints -- Microsoft Planner via Graph API (Backend-only, Showcase)."""

import logging
import os
import sys

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.config import get_settings
from app.models import User

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "email-graph"))
from graph_client import GraphClient, GraphConfig  # noqa: E402

logger = logging.getLogger("taskpilot.planner")
router = APIRouter(prefix="/api/planner", tags=["planner"])

_graph_client: GraphClient | None = None


def _get_graph_client() -> GraphClient:
    global _graph_client
    if _graph_client is None:
        s = get_settings()
        config = GraphConfig(
            tenant_id=s.graph_tenant_id,
            client_id=s.graph_client_id,
            client_secret=s.graph_client_secret,
            user_email=s.graph_user_email,
        )
        _graph_client = GraphClient(config)
    return _graph_client


def _require_owner(user: User) -> None:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Nur Owner dürfen auf Planner zugreifen")


def _check_configured() -> None:
    s = get_settings()
    if not all([s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_user_email]):
        raise HTTPException(
            status_code=503,
            detail="Graph API nicht konfiguriert. Setze TP_GRAPH_* in der Umgebung.",
        )


@router.get("/plans")
async def list_plans(user: User = Depends(get_current_user)):
    """Alle Planner-Pläne des Users."""
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        plans = await client.list_planner_plans()
        return [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "createdDateTime": p.get("createdDateTime"),
            }
            for p in plans
        ]
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("list_plans fehlgeschlagen: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/tasks")
async def list_tasks(
    top: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """Eigene Planner-Aufgaben."""
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        tasks = await client.list_planner_tasks(top=top)
        return [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "percentComplete": t.get("percentComplete"),
                "dueDateTime": t.get("dueDateTime"),
                "createdDateTime": t.get("createdDateTime"),
                "planId": t.get("planId"),
                "bucketId": t.get("bucketId"),
            }
            for t in tasks
        ]
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("list_tasks fehlgeschlagen: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    user: User = Depends(get_current_user),
):
    """Einzelne Planner-Aufgabe mit Details."""
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        task = await client.get_planner_task(task_id)
        details = {}
        try:
            details = await client.get_planner_task_details(task_id)
        except Exception:
            pass
        task["details"] = details
        return task
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("get_task fehlgeschlagen: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


class CreatePlannerTask(BaseModel):
    plan_id: str
    title: str
    bucket_id: str | None = None
    due_date: str | None = None


@router.post("/tasks")
async def create_task(
    body: CreatePlannerTask,
    user: User = Depends(get_current_user),
):
    """Neue Planner-Aufgabe erstellen."""
    _require_owner(user)
    _check_configured()
    client = _get_graph_client()
    try:
        task = await client.create_planner_task(
            plan_id=body.plan_id,
            title=body.title,
            bucket_id=body.bucket_id,
            due_date=body.due_date,
        )
        return {
            "id": task.get("id"),
            "title": task.get("title"),
            "status": "created",
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("create_task fehlgeschlagen: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

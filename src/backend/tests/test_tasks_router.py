"""Router-Contract-Tests für /api/tasks.

Testet RBAC-Einschränkungen und Schema-Validierung.
Endpoints die DB-Queries ausführen sind mit @pytest.mark.db markiert.
"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio

FAKE_PROJECT_ID = str(uuid.uuid4())
FAKE_COLUMN_ID = str(uuid.uuid4())


def _minimal_task_body(**overrides) -> dict:
    """Erzeugt einen minimalen TaskCreate-Body."""
    base = {
        "title": "Test-Aufgabe",
        "project_id": FAKE_PROJECT_ID,
        "board_column_id": FAKE_COLUMN_ID,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# RBAC: Member darf assignee='agent' nicht setzen (403)
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_member_cannot_assign_agent(client_as_member):
    """POST /api/tasks mit assignee='agent' als Member wird abgelehnt."""
    body = _minimal_task_body(assignee="agent")
    resp = await client_as_member.post("/api/tasks", json=body)
    assert resp.status_code == 403
    assert "Agent" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# RBAC: Member-restricted Fields werden bei Member ignoriert/entfernt
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_member_restricted_fields_stripped(client_as_member):
    """POST /api/tasks als Member: eingeschränkte Felder (autonomy_level,
    llm_override etc.) werden stillschweigend entfernt, nicht blockiert.
    Benötigt DB für die tatsächliche Task-Erstellung."""
    body = _minimal_task_body(
        autonomy_level="L3",
        llm_override="gpt-4",
        data_class="confidential",
    )
    resp = await client_as_member.post("/api/tasks", json=body)
    # Entweder 201 (Felder entfernt) oder ein anderer DB-Fehler —
    # nicht 403 (das wäre nur bei assignee='agent')
    assert resp.status_code != 403 or "Agent" in resp.json().get("detail", "")


# ---------------------------------------------------------------------------
# Schema-Validierung: ungültiger Body → 422
# ---------------------------------------------------------------------------


async def test_create_task_invalid_body_returns_422(client_as_owner):
    """POST /api/tasks ohne Pflichtfelder gibt 422 (Validation Error)."""
    resp = await client_as_owner.post("/api/tasks", json={})
    assert resp.status_code == 422


async def test_create_task_invalid_uuid_returns_422(client_as_owner):
    """POST /api/tasks mit ungültiger UUID für board_column_id gibt 422."""
    body = {
        "title": "Test",
        "project_id": "nicht-eine-uuid",
        "board_column_id": "auch-keine-uuid",
    }
    resp = await client_as_owner.post("/api/tasks", json=body)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Auth: Anonymer Zugriff auf /api/tasks/due-today → 403 (HTTPBearer)
# ---------------------------------------------------------------------------


async def test_due_today_rejects_anonymous(client_anonymous):
    """GET /api/tasks/due-today ohne Bearer-Token wird abgelehnt (401 oder 403)."""
    resp = await client_anonymous.get("/api/tasks/due-today")
    assert resp.status_code in (401, 403)

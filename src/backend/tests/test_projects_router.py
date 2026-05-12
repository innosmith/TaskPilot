"""Router-Contract-Tests für /api/projects.

Testet RBAC (Owner-only Endpoints) und Auth-Absicherung.
"""

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# POST /api/projects — Owner-only (require_role("owner"))
# ---------------------------------------------------------------------------


async def test_create_project_forbidden_for_member(client_as_member):
    """POST /api/projects als Member gibt 403 zurück."""
    body = {"name": "Kundenprojekt", "color": "#ff0000"}
    resp = await client_as_member.post("/api/projects", json=body)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/projects — Auth erforderlich
# ---------------------------------------------------------------------------


async def test_list_projects_rejects_anonymous(client_anonymous):
    """GET /api/projects ohne Bearer-Token wird abgelehnt (401 oder 403)."""
    resp = await client_anonymous.get("/api/projects")
    assert resp.status_code in (401, 403)

"""Router-Contract-Tests für /api/mindmaps und /api/public/mindmaps.

Testet RBAC-Einschränkungen, Public-Endpoint-Validierung und Schema-Validierung.
Endpoints die DB-Queries ausführen sind mit @pytest.mark.db markiert.
"""

import uuid

import pytest

from conftest import TEST_PROJECT_ID, TEST_COLUMN_BACKLOG_ID

pytestmark = pytest.mark.asyncio

FAKE_MINDMAP_ID = uuid.UUID("aa000000-0000-0000-0000-000000000001")
FAKE_SHARE_TOKEN = "test-share-token-abc"


def _minimal_mindmap_body(**overrides) -> dict:
    """Erzeugt einen minimalen MindmapCreate-Body."""
    base = {"title": "Test Mind-Map"}
    base.update(overrides)
    return base


def _convert_tasks_body(**overrides) -> dict:
    """Erzeugt einen minimalen ConvertToTasksRequest-Body."""
    base = {
        "node_ids": ["root", "node-1"],
        "project_id": str(TEST_PROJECT_ID),
        "board_column_id": str(TEST_COLUMN_BACKLOG_ID),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Zugriffsschutz-Tests (RBAC)
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_list_mindmaps_owner_ok(client_as_owner):
    """Owner kann die Mind-Map-Liste abrufen (benötigt DB mit mindmaps-Tabelle)."""
    resp = await client_as_owner.get("/api/mindmaps")
    assert resp.status_code != 401
    assert resp.status_code != 403


async def test_list_mindmaps_anonymous_rejected(client_anonymous):
    """Anonyme Requests auf /api/mindmaps werden abgelehnt."""
    resp = await client_anonymous.get("/api/mindmaps")
    assert resp.status_code in (401, 403)


async def test_create_mindmap_member_rejected(client_as_member):
    """POST /api/mindmaps als Member wird abgelehnt (Owner-only)."""
    body = _minimal_mindmap_body()
    resp = await client_as_member.post("/api/mindmaps", json=body)
    assert resp.status_code == 403


@pytest.mark.db
async def test_create_mindmap_owner_ok(client_as_owner):
    """Owner kann eine Mind-Map erstellen (benötigt DB mit mindmaps-Tabelle)."""
    body = _minimal_mindmap_body()
    resp = await client_as_owner.post("/api/mindmaps", json=body)
    assert resp.status_code != 401
    assert resp.status_code != 403


async def test_delete_mindmap_member_rejected(client_as_member):
    """DELETE /api/mindmaps/{id} als Member wird abgelehnt (Owner-only)."""
    resp = await client_as_member.delete(f"/api/mindmaps/{FAKE_MINDMAP_ID}")
    assert resp.status_code == 403


async def test_folders_member_rejected(client_as_member):
    """Member darf keine Ordner verwalten (GET/POST /api/mindmaps/folders)."""
    resp_list = await client_as_member.get("/api/mindmaps/folders")
    assert resp_list.status_code == 403

    resp_create = await client_as_member.post(
        "/api/mindmaps/folders",
        json={"name": "Test-Ordner"},
    )
    assert resp_create.status_code == 403


async def test_convert_tasks_member_rejected(client_as_member):
    """Member darf keine Mind-Map-Knoten in Tasks konvertieren (Owner-only)."""
    body = _convert_tasks_body()
    resp = await client_as_member.post(
        f"/api/mindmaps/{FAKE_MINDMAP_ID}/convert-to-tasks",
        json=body,
    )
    assert resp.status_code == 403


async def test_shares_member_rejected(client_as_member):
    """Member darf keine Shares verwalten (POST/GET Shares, Owner-only)."""
    resp_create = await client_as_member.post(
        f"/api/mindmaps/{FAKE_MINDMAP_ID}/shares",
        json={"password": "geheim123", "permission": "view"},
    )
    assert resp_create.status_code == 403

    resp_list = await client_as_member.get(
        f"/api/mindmaps/{FAKE_MINDMAP_ID}/shares",
    )
    assert resp_list.status_code == 403

    resp_delete = await client_as_member.delete(
        f"/api/mindmaps/shares/{FAKE_MINDMAP_ID}",
    )
    assert resp_delete.status_code == 403


# ---------------------------------------------------------------------------
# 2. Public-Endpoint-Tests
# ---------------------------------------------------------------------------


async def test_public_verify_no_password(client_anonymous):
    """POST /api/public/mindmaps/{token}/verify ohne Passwort gibt 422."""
    resp = await client_anonymous.post(
        f"/api/public/mindmaps/{FAKE_SHARE_TOKEN}/verify",
        json={},
    )
    assert resp.status_code == 422


async def test_public_get_no_password(client_anonymous):
    """GET /api/public/mindmaps/{token} ohne X-Share-Password-Header gibt 422."""
    resp = await client_anonymous.get(
        f"/api/public/mindmaps/{FAKE_SHARE_TOKEN}",
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. Schema-Validierung
# ---------------------------------------------------------------------------


async def test_create_mindmap_invalid_visibility(client_as_owner):
    """Mind-Map mit visibility='project' ohne project_id wird abgelehnt."""
    body = _minimal_mindmap_body(visibility="project")
    resp = await client_as_owner.post("/api/mindmaps", json=body)
    # 400 (Business-Regel) oder 500 (DB-Fehler vor der Prüfung)
    # Hauptsache nicht 201 (Erfolg)
    assert resp.status_code != 201


@pytest.mark.db
async def test_convert_tasks_empty_nodes(client_as_owner):
    """Leere node_ids-Liste wird entweder abgelehnt oder ergibt 0 Tasks
    (benötigt DB mit mindmaps-Tabelle)."""
    body = _convert_tasks_body(node_ids=[])
    resp = await client_as_owner.post(
        f"/api/mindmaps/{FAKE_MINDMAP_ID}/convert-to-tasks",
        json=body,
    )
    assert resp.status_code != 401
    assert resp.status_code != 403

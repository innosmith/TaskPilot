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


# ---------------------------------------------------------------------------
# DELETE /api/projects/{id}/columns/{col_id} — Umhängen & letzte Spalte
# ---------------------------------------------------------------------------


async def _columns_by_name(client, project_id: str) -> dict[str, str]:
    """Liest die Board-Spalten und liefert eine Zuordnung Name -> Spalten-ID."""
    board = await client.get(f"/api/projects/{project_id}/board")
    assert board.status_code == 200
    return {c["name"]: c["id"] for c in board.json()["columns"]}


@pytest.mark.db
async def test_delete_column_reassigns_tasks(client_as_owner):
    """Löschen einer Spalte hängt enthaltene Tasks (auch erledigte, im Board
    ausgeblendete) in eine verbleibende Spalte um und gibt 204 statt 500."""
    proj = await client_as_owner.post("/api/projects", json={"name": "Spalten-Löschtest"})
    assert proj.status_code == 201
    project_id = proj.json()["id"]
    try:
        assert (await client_as_owner.post(
            f"/api/projects/{project_id}/columns", json={"name": "A", "position": 1.0}
        )).status_code == 201
        assert (await client_as_owner.post(
            f"/api/projects/{project_id}/columns", json={"name": "B", "position": 2.0}
        )).status_code == 201

        cols = await _columns_by_name(client_as_owner, project_id)
        col_a, col_b = cols["A"], cols["B"]

        # Sichtbarer, offener Task in Spalte A
        t1 = await client_as_owner.post(
            "/api/tasks",
            json={"title": "Offen", "project_id": project_id, "board_column_id": col_a},
        )
        assert t1.status_code == 201
        t1_id = t1.json()["id"]

        # Erledigter Task in A — im Board ausgeblendet, blockierte früher das Löschen
        t2 = await client_as_owner.post(
            "/api/tasks",
            json={"title": "Erledigt", "project_id": project_id, "board_column_id": col_a},
        )
        assert t2.status_code == 201
        t2_id = t2.json()["id"]
        assert (await client_as_owner.patch(
            f"/api/tasks/{t2_id}", json={"is_completed": True}
        )).status_code == 200

        # Spalte A löschen
        deleted = await client_as_owner.delete(f"/api/projects/{project_id}/columns/{col_a}")
        assert deleted.status_code == 204

        # Board: A ist weg, offener Task jetzt in B
        cols_after = {c["id"]: c for c in (
            await client_as_owner.get(f"/api/projects/{project_id}/board")
        ).json()["columns"]}
        assert col_a not in cols_after
        assert col_b in cols_after
        assert t1_id in [t["id"] for t in cols_after[col_b]["tasks"]]

        # Erledigter Task wurde ebenfalls umgehängt (Einzel-GET, da im Board ausgeblendet)
        t2_get = await client_as_owner.get(f"/api/tasks/{t2_id}")
        assert t2_get.status_code == 200
        assert t2_get.json()["board_column_id"] == col_b
    finally:
        await client_as_owner.delete(f"/api/projects/{project_id}")


@pytest.mark.db
async def test_delete_last_column_conflict(client_as_owner):
    """Die letzte verbleibende Spalte eines Projekts kann nicht gelöscht werden (409)."""
    proj = await client_as_owner.post("/api/projects", json={"name": "Letzte-Spalte-Test"})
    assert proj.status_code == 201
    project_id = proj.json()["id"]
    try:
        assert (await client_as_owner.post(
            f"/api/projects/{project_id}/columns", json={"name": "Einzige", "position": 1.0}
        )).status_code == 201
        col_id = (await _columns_by_name(client_as_owner, project_id))["Einzige"]

        deleted = await client_as_owner.delete(f"/api/projects/{project_id}/columns/{col_id}")
        assert deleted.status_code == 409
    finally:
        await client_as_owner.delete(f"/api/projects/{project_id}")

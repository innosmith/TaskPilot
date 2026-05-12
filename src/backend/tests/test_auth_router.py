"""Router-Contract-Tests für /api/auth.

Testet Auth-Endpoints über httpx AsyncClient mit Dependency-Overrides.
Kein DB-, JWT- oder API-Zugriff nötig für /me (GET).
"""

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# GET /api/auth/me — Dependency-Override liefert FakeUser, kein DB nötig
# ---------------------------------------------------------------------------


async def test_me_returns_owner_data(client_as_owner, owner_user):
    """GET /me gibt die Owner-Daten korrekt zurück."""
    resp = await client_as_owner.get("/api/auth/me")
    assert resp.status_code == 200

    data = resp.json()
    assert data["id"] == str(owner_user.id)
    assert data["email"] == owner_user.email
    assert data["role"] == "owner"
    assert data["display_name"] == owner_user.display_name
    assert data["is_active"] is True


async def test_me_returns_member_data(client_as_member, member_user):
    """GET /me gibt die Member-Daten korrekt zurück."""
    resp = await client_as_member.get("/api/auth/me")
    assert resp.status_code == 200

    data = resp.json()
    assert data["id"] == str(member_user.id)
    assert data["email"] == member_user.email
    assert data["role"] == "member"


async def test_me_rejects_anonymous(client_anonymous):
    """GET /me ohne Bearer-Token wird von HTTPBearer abgelehnt (401 oder 403)."""
    resp = await client_anonymous.get("/api/auth/me")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PATCH /api/auth/me — braucht DB (flush), daher mit Marker
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_patch_me_owner_updates_display_name(client_as_owner):
    """PATCH /me aktualisiert display_name für Owner (benötigt DB)."""
    resp = await client_as_owner.patch(
        "/api/auth/me",
        json={"display_name": "Anthony Updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Anthony Updated"


@pytest.mark.db
async def test_patch_me_member_updates_display_name(client_as_member):
    """PATCH /me aktualisiert display_name für Member (benötigt DB)."""
    resp = await client_as_member.patch(
        "/api/auth/me",
        json={"display_name": "Kunde Updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Kunde Updated"

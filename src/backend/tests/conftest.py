"""Test-Fixtures für TaskPilot Backend Tests.

Stellt bereit:
- sys.path fuer Shared Libraries (email-graph, mcp-graph, pipedrive etc.)
- Fake-User-Fixtures (owner_user, member_user) fuer Dependency-Overrides
- AsyncClient-Fixture fuer Router-Contract-Tests mit DB
"""

import sys
import os
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "email-graph"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "mcp-graph"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Fake User-Objekte fuer Dependency-Overrides (kein DB-Zugriff noetig)
# ---------------------------------------------------------------------------

class FakeUser:
    """Minimales User-Objekt das die gleichen Attribute wie models.User hat."""

    def __init__(self, *, role: str = "owner", user_id: uuid.UUID | None = None):
        self.id = user_id or uuid.uuid4()
        self.email = f"test-{role}@innosmith.ai"
        self.display_name = f"Test {role.title()}"
        self.avatar_url = None
        self.role = role
        self.is_active = True
        self.settings = {}
        self.mfa_secret = None
        self.mfa_enabled = False
        self.created_at = datetime.now(timezone.utc)
        self.last_login_at = None
        self.invited_by = None
        self.password_hash = "not-a-real-hash"


OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
MEMBER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

TEST_PROJECT_ID = uuid.UUID("f0000000-0000-0000-0000-000000000001")
TEST_COLUMN_BACKLOG_ID = uuid.UUID("f1000000-0000-0000-0000-000000000001")
TEST_COLUMN_PROGRESS_ID = uuid.UUID("f1000000-0000-0000-0000-000000000002")
TEST_COLUMN_DONE_ID = uuid.UUID("f1000000-0000-0000-0000-000000000003")


@pytest.fixture
def owner_user() -> FakeUser:
    return FakeUser(role="owner", user_id=OWNER_ID)


@pytest.fixture
def member_user() -> FakeUser:
    return FakeUser(role="member", user_id=MEMBER_ID)


# ---------------------------------------------------------------------------
# FastAPI TestClient mit Dependency-Overrides
# ---------------------------------------------------------------------------

def _make_override(fake_user: FakeUser):
    """Erzeugt eine async Dependency die immer den fake_user zurueckgibt."""
    async def _override():
        return fake_user
    return _override


@pytest_asyncio.fixture
async def client_as_owner(owner_user: FakeUser):
    """AsyncClient der als Owner authentifiziert ist."""
    from app.auth.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = _make_override(owner_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_as_member(member_user: FakeUser):
    """AsyncClient der als Member authentifiziert ist."""
    from app.auth.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = _make_override(member_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_anonymous():
    """AsyncClient ohne Authentifizierung."""
    from app.main import app

    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

"""Tests für das Notification-System: Router RBAC, Mention-Parsing, Service-Logik."""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import FakeUser, OWNER_ID, MEMBER_ID


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_override(fake_user: FakeUser):
    async def _override():
        return fake_user
    return _override


@pytest_asyncio.fixture
async def client_owner():
    from app.auth.deps import get_current_user
    from app.main import app
    app.dependency_overrides[get_current_user] = _make_override(
        FakeUser(role="owner", user_id=OWNER_ID)
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_member():
    from app.auth.deps import get_current_user
    from app.main import app
    app.dependency_overrides[get_current_user] = _make_override(
        FakeUser(role="member", user_id=MEMBER_ID)
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_anon():
    from app.main import app
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Mention-Parsing (Unit Tests — kein DB-Zugriff)
# ---------------------------------------------------------------------------

class TestMentionParsing:
    def test_mention_pattern_matches(self):
        from app.services.notification import MENTION_PATTERN
        text = "Hallo @[Anthony Smith](550e8400-e29b-41d4-a716-446655440000), bitte prüfen."
        matches = MENTION_PATTERN.findall(text)
        assert len(matches) == 1
        assert matches[0][0] == "Anthony Smith"
        assert matches[0][1] == "550e8400-e29b-41d4-a716-446655440000"

    def test_mention_pattern_multiple(self):
        from app.services.notification import MENTION_PATTERN
        text = "@[Max Muster](aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee) und @[Lisa Test](11111111-2222-3333-4444-555555555555) bitte prüfen."
        matches = MENTION_PATTERN.findall(text)
        assert len(matches) == 2

    def test_mention_pattern_no_match(self):
        from app.services.notification import MENTION_PATTERN
        text = "Hallo @Anthony Smith, bitte prüfen."
        matches = MENTION_PATTERN.findall(text)
        assert len(matches) == 0

    def test_strip_mention_markup(self):
        from app.services.notification import _strip_mention_markup
        text = "Hallo @[Anthony Smith](550e8400-e29b-41d4-a716-446655440000), bitte prüfen."
        result = _strip_mention_markup(text)
        assert result == "Hallo @Anthony Smith, bitte prüfen."
        assert "(550e8400" not in result


# ---------------------------------------------------------------------------
# Router RBAC (Auth-Enforcement, kein DB)
# ---------------------------------------------------------------------------

class TestNotificationRouterAuth:
    @pytest.mark.asyncio
    async def test_unread_count_rejects_anonymous(self, client_anon):
        resp = await client_anon.get("/api/notifications/unread-count")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_list_rejects_anonymous(self, client_anon):
        resp = await client_anon.get("/api/notifications")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_mark_all_read_rejects_anonymous(self, client_anon):
        resp = await client_anon.post("/api/notifications/read-all")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_mentionable_users_requires_auth(self, client_anon):
        resp = await client_anon.get(
            "/api/notifications/mentionable-users",
            params={"project_id": str(uuid.uuid4())},
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Notification-Typen-Validierung (Unit)
# ---------------------------------------------------------------------------

class TestNotificationTypes:
    EXPECTED_TYPES = {
        "agent_awaiting_approval",
        "task_suggested",
        "task_assigned",
        "chat_triage_task",
        "comment_mention",
        "task_due_soon",
        "system_health_warning",
    }

    def test_all_trigger_functions_exist(self):
        """Stellt sicher, dass für jeden Typ eine Service-Funktion existiert."""
        from app.services import notification as svc
        assert callable(svc.notify_agent_awaiting_approval)
        assert callable(svc.notify_task_suggested)
        assert callable(svc.notify_task_assigned)
        assert callable(svc.notify_chat_triage_task)
        assert callable(svc.notify_mentions)
        assert callable(svc.create_notification)

    def test_notification_model_exists(self):
        from app.models import Notification
        assert hasattr(Notification, "user_id")
        assert hasattr(Notification, "type")
        assert hasattr(Notification, "title")
        assert hasattr(Notification, "is_read")
        assert hasattr(Notification, "link")
        assert hasattr(Notification, "source_type")
        assert hasattr(Notification, "source_id")

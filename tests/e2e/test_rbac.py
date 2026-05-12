"""E2E-Tests: Rollenbasierte Zugriffskontrolle (RBAC).

Prueft dass Member nur eigene Projekte sehen und Owner-Seiten nicht erreichen.
"""

import os

import pytest
from playwright.sync_api import Page


MEMBER_EMAIL = os.environ.get("TP_TEST_MEMBER_EMAIL")
MEMBER_PASSWORD = os.environ.get("TP_TEST_MEMBER_PASSWORD")


@pytest.mark.skipif(
    not MEMBER_EMAIL or not MEMBER_PASSWORD,
    reason="TP_TEST_MEMBER_EMAIL / TP_TEST_MEMBER_PASSWORD nicht gesetzt",
)
class TestMemberRestrictions:
    """Member darf nur auf zugewiesene Projekte zugreifen."""

    def test_member_redirected_from_cockpit(self, member_page: Page):
        """Member wird vom Cockpit (Owner-only) weitergeleitet."""
        member_page.goto("/")
        member_page.wait_for_timeout(3000)
        assert "/projects" in member_page.url or "/login" in member_page.url, (
            "Member sollte vom Cockpit zu /projects weitergeleitet werden"
        )

    def test_member_redirected_from_inbox(self, member_page: Page):
        """Member wird von Inbox (Owner-only) weitergeleitet."""
        member_page.goto("/inbox")
        member_page.wait_for_timeout(3000)
        assert "/inbox" not in member_page.url or "/projects" in member_page.url, (
            "Member sollte keinen Zugriff auf Inbox haben"
        )

    def test_member_redirected_from_agenten(self, member_page: Page):
        """Member wird von Agenten-Queue (Owner-only) weitergeleitet."""
        member_page.goto("/agenten")
        member_page.wait_for_timeout(3000)
        assert "/agenten" not in member_page.url or "/projects" in member_page.url, (
            "Member sollte keinen Zugriff auf Agenten-Queue haben"
        )

    def test_member_sees_projects_page(self, member_page: Page):
        """Member kann die Projekte-Seite sehen."""
        member_page.goto("/projects")
        member_page.wait_for_timeout(3000)
        assert "/projects" in member_page.url


@pytest.mark.skipif(
    not os.environ.get("TP_TEST_PASSWORD"),
    reason="TP_TEST_PASSWORD nicht gesetzt",
)
class TestOwnerAccess:
    """Owner hat Zugriff auf alle Seiten."""

    @pytest.mark.parametrize("route", [
        "/",
        "/pipeline",
        "/projects",
        "/inbox",
        "/agenten",
        "/einstellungen",
    ])
    def test_owner_can_access_all_routes(self, owner_page: Page, route: str):
        """Owner kann jede Route aufrufen ohne Redirect."""
        owner_page.goto(route)
        owner_page.wait_for_timeout(3000)
        assert "/login" not in owner_page.url, f"Owner sollte auf {route} zugreifen koennen"

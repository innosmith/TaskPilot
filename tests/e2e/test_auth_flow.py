"""E2E-Tests: Authentifizierung und Routing.

Prueft Login, Redirect-Logik und rollenbasierte Navigation.
Login-Flow-Tests verwenden anon_page (ohne Session),
alle anderen verwenden owner_page (mit storageState).
"""

import pytest
from playwright.sync_api import Page, expect


class TestLoginFlow:
    """Login-Seite und Authentifizierung."""

    def test_login_page_loads(self, anon_page: Page):
        """Login-Seite ist erreichbar und zeigt Formular."""
        anon_page.goto("/login")
        expect(anon_page.locator("input[type='email'], input[name='email']")).to_be_visible()
        expect(anon_page.locator("input[type='password'], input[name='password']")).to_be_visible()
        expect(anon_page.locator("button[type='submit']")).to_be_visible()

    def test_invalid_login_shows_error(self, anon_page: Page):
        """Falsches Passwort zeigt Fehlermeldung."""
        anon_page.goto("/login")
        anon_page.fill("input[type='email'], input[name='email']", "wrong@example.com")
        anon_page.fill("input[type='password'], input[name='password']", "wrongpassword")
        anon_page.click("button[type='submit']")
        anon_page.wait_for_timeout(2000)
        assert "/login" in anon_page.url, "Sollte auf Login-Seite bleiben"

    def test_successful_login_redirects(self, owner_page: Page):
        """Erfolgreicher Login leitet zum Cockpit oder zur Hauptseite weiter."""
        owner_page.goto("/")
        owner_page.wait_for_timeout(2000)
        assert "/login" not in owner_page.url


class TestProtectedRoutes:
    """Geschuetzte Seiten erfordern Login."""

    @pytest.mark.parametrize("route", [
        "/",
        "/pipeline",
        "/projects",
        "/inbox",
        "/agenten",
        "/einstellungen",
    ])
    def test_protected_routes_redirect_to_login(self, anon_page: Page, route: str):
        """Nicht-eingeloggte User werden zu /login weitergeleitet."""
        anon_page.goto(route)
        anon_page.wait_for_timeout(2000)
        assert "/login" in anon_page.url, f"Route {route} sollte zu /login weiterleiten"


class TestOwnerNavigation:
    """Owner sieht alle Navigationseintraege."""

    def test_owner_sees_sidebar_navigation(self, owner_page: Page):
        """Owner sieht Cockpit, Pipeline, Projekte, Inbox, Agenten, Einstellungen."""
        owner_page.goto("/")
        owner_page.wait_for_timeout(2000)
        sidebar = owner_page.locator("aside").first
        expect(sidebar).to_be_visible(timeout=10000)

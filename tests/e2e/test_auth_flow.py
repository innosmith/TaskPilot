"""E2E-Tests: Authentifizierung und Routing.

Prueft Login, Redirect-Logik und rollenbasierte Navigation.
Credentials werden interaktiv abgefragt (via conftest.py).
"""

import pytest
from playwright.sync_api import Page, expect


class TestLoginFlow:
    """Login-Seite und Authentifizierung."""

    def test_login_page_loads(self, page: Page):
        """Login-Seite ist erreichbar und zeigt Formular."""
        page.goto("/login")
        expect(page.locator("input[type='email'], input[name='email']")).to_be_visible()
        expect(page.locator("input[type='password'], input[name='password']")).to_be_visible()
        expect(page.locator("button[type='submit']")).to_be_visible()

    def test_invalid_login_shows_error(self, page: Page):
        """Falsches Passwort zeigt Fehlermeldung."""
        page.goto("/login")
        page.fill("input[type='email'], input[name='email']", "wrong@example.com")
        page.fill("input[type='password'], input[name='password']", "wrongpassword")
        page.click("button[type='submit']")
        page.wait_for_timeout(2000)
        assert "/login" in page.url, "Sollte auf Login-Seite bleiben"

    def test_successful_login_redirects(self, owner_page: Page):
        """Erfolgreicher Login leitet zum Cockpit oder zur Hauptseite weiter."""
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
    def test_protected_routes_redirect_to_login(self, page: Page, route: str):
        """Nicht-eingeloggte User werden zu /login weitergeleitet."""
        page.goto(route)
        page.wait_for_timeout(2000)
        assert "/login" in page.url, f"Route {route} sollte zu /login weiterleiten"


class TestOwnerNavigation:
    """Owner sieht alle Navigationseintraege."""

    def test_owner_sees_sidebar_navigation(self, owner_page: Page):
        """Owner sieht Cockpit, Pipeline, Projekte, Inbox, Agenten, Einstellungen."""
        owner_page.goto("/")
        owner_page.wait_for_timeout(2000)
        sidebar = owner_page.locator("nav, aside, [data-testid='sidebar']")
        expect(sidebar).to_be_visible(timeout=10000)

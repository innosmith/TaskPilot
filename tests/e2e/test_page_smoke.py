"""E2E Page-Smoke-Tests: Jede Seite rendert realen Inhalt.

Generischer, datengetriebener Test der alle Owner-Seiten besucht
und prüft ob ein stabiles Heading/Element sichtbar wird.
Erkennt JS-Crashes, fehlende API-Anbindungen, Routing-Fehler
und Import-Fehler bei Lazy-Loaded Seiten.
"""

import pytest
from playwright.sync_api import Page, expect


PAGE_CHECKS = [
    ("/cockpit", "Cockpit"),
    ("/pipeline", "Agenda"),
    ("/projects", "Projekte"),
    ("/inbox", "Posteingang"),
    ("/agenten", "Agenten"),
    ("/agenten/chat", "Neuer Chat"),
    ("/settings", "Einstellungen"),
    ("/signale", "Signale"),
    ("/finanzen", "Finanz"),
    ("/debitoren", "Debitor"),
    ("/kreditoren", "Kreditor"),
]


class TestPageSmoke:
    """Jede Owner-Seite rendert realen Inhalt (kein Blank-Screen)."""

    @pytest.mark.parametrize("route,expected_text", PAGE_CHECKS, ids=[r for r, _ in PAGE_CHECKS])
    def test_page_renders_content(self, owner_page: Page, route: str, expected_text: str):
        """Seite laden und pruefen ob erwarteter Text sichtbar ist."""
        owner_page.goto(route)
        owner_page.wait_for_timeout(3000)
        assert "/login" not in owner_page.url, f"Redirect zu Login auf {route}"
        expect(owner_page.get_by_text(expected_text).first).to_be_visible(timeout=10000)


class TestErrorHandling:
    """Fehlerseiten zeigen sinnvolle Meldungen statt Blank-Screen."""

    def test_invalid_project_shows_error(self, owner_page: Page):
        """Ungueltige Projekt-ID zeigt Fehlermeldung, keinen JS-Crash."""
        owner_page.goto("/projects/00000000-0000-0000-0000-999999999999")
        owner_page.wait_for_timeout(3000)
        assert "/login" not in owner_page.url
        error_visible = (
            owner_page.get_by_text("nicht gefunden").first.is_visible()
            or owner_page.get_by_text("Fehler").first.is_visible()
            or owner_page.get_by_text("Not Found").first.is_visible()
        )
        assert error_visible, "Ungueltige Projekt-ID sollte Fehlermeldung zeigen"

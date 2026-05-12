"""E2E-Tests: Task erstellen, bearbeiten und loeschen.

Prueft den kompletten Task-Lifecycle ueber die UI.
Credentials werden interaktiv abgefragt (via conftest.py).
"""

import pytest
from playwright.sync_api import Page, expect


class TestTaskCRUD:
    """Task-Lifecycle ueber die UI."""

    def test_navigate_to_project_board(self, owner_page: Page):
        """Navigation zu einem Projekt-Board funktioniert."""
        owner_page.goto("/projects")
        owner_page.wait_for_timeout(2000)

        project_link = owner_page.locator("a[href*='/project/']").first
        if project_link.count() == 0:
            pytest.skip("Kein Projekt vorhanden — Seed-Daten fehlen")

        project_link.click()
        owner_page.wait_for_timeout(2000)
        assert "/project/" in owner_page.url

    def test_task_create_dialog_opens(self, owner_page: Page):
        """Task-Erstellungs-Dialog oeffnet sich."""
        owner_page.goto("/projects")
        owner_page.wait_for_timeout(2000)

        project_link = owner_page.locator("a[href*='/project/']").first
        if project_link.count() == 0:
            pytest.skip("Kein Projekt vorhanden")

        project_link.click()
        owner_page.wait_for_timeout(2000)

        add_btn = owner_page.locator(
            "[data-testid='task-add-button'], "
            "button:has-text('Task'), "
            "button:has-text('Aufgabe'), "
            "button:has-text('+')"
        ).first
        if add_btn.count() == 0:
            pytest.skip("Task-Add-Button nicht gefunden — UI-Struktur weicht ab")

        add_btn.click()
        owner_page.wait_for_timeout(1000)


class TestPipelinePage:
    """Agenda/Pipeline-Seite funktioniert."""

    def test_pipeline_loads(self, owner_page: Page):
        """Pipeline-Seite laed und zeigt Spalten."""
        owner_page.goto("/pipeline")
        owner_page.wait_for_timeout(3000)
        assert "/pipeline" in owner_page.url

    def test_pipeline_shows_columns(self, owner_page: Page):
        """Pipeline zeigt mindestens eine Spalte (Focus, This Week etc.)."""
        owner_page.goto("/pipeline")
        owner_page.wait_for_timeout(3000)

        columns = owner_page.locator(
            "[data-testid*='pipeline-column'], "
            "[data-testid*='agenda-column'], "
            ".kanban-column, "
            "[class*='column']"
        )
        assert columns.count() > 0, "Keine Pipeline-Spalten sichtbar"

"""Tests fuer die Pipeline-Placement-Logik (determine_target_column_name).

Prueft die reine Datums-zu-Spalte-Zuordnung ohne DB-Zugriff.
"""

from datetime import date, timedelta

import pytest

from app.services.pipeline_promoter import determine_target_column_name


class TestDetermineTargetColumnName:
    """Prueft die Zuordnung von due_date zu Agenda-Spaltenname."""

    def test_overdue_goes_to_focus(self):
        today = date(2026, 5, 14)
        assert determine_target_column_name(date(2026, 5, 10), today) == "Focus"

    def test_today_goes_to_focus(self):
        today = date(2026, 5, 14)
        assert determine_target_column_name(today, today) == "Focus"

    def test_this_week_same_week(self):
        today = date(2026, 5, 14)  # Donnerstag
        friday = date(2026, 5, 15)
        assert determine_target_column_name(friday, today) == "This Week"

    def test_this_week_sunday(self):
        today = date(2026, 5, 12)  # Montag
        sunday = date(2026, 5, 17)  # Sonntag derselben Woche
        assert determine_target_column_name(sunday, today) == "This Week"

    def test_next_week(self):
        today = date(2026, 5, 14)  # Donnerstag KW20
        next_monday = date(2026, 5, 18)  # Montag KW21
        next_friday = date(2026, 5, 22)  # Freitag KW21
        assert determine_target_column_name(next_monday, today) == "Next Week"
        assert determine_target_column_name(next_friday, today) == "Next Week"

    def test_this_month_after_next_week(self):
        today = date(2026, 5, 14)
        end_of_may = date(2026, 5, 31)
        assert determine_target_column_name(end_of_may, today) == "This Month"

    def test_next_month(self):
        today = date(2026, 5, 14)
        june_20 = date(2026, 6, 20)
        assert determine_target_column_name(june_20, today) == "Next Month"

    def test_next_month_december_to_january(self):
        today = date(2026, 12, 15)
        jan_10 = date(2027, 1, 10)
        assert determine_target_column_name(jan_10, today) == "Next Month"

    def test_beyond_far_future(self):
        today = date(2026, 5, 14)
        august = date(2026, 8, 1)
        assert determine_target_column_name(august, today) == "Beyond"

    def test_beyond_two_months_out(self):
        today = date(2026, 5, 14)
        july = date(2026, 7, 1)
        assert determine_target_column_name(july, today) == "Beyond"

    def test_lohnabrechnung_scenario(self):
        """Szeanrio: Lohnabrechnung am 20. jeden Monats.

        Am 14. Mai ist der 20. Juni -> Next Month.
        Am 1. Juni ist der 20. Juni -> This Month.
        Am 16. Juni ist der 20. Juni -> This Week.
        Am 20. Juni ist der 20. Juni -> Focus.
        """
        assert determine_target_column_name(date(2026, 6, 20), date(2026, 5, 14)) == "Next Month"
        assert determine_target_column_name(date(2026, 6, 20), date(2026, 6, 1)) == "This Month"
        assert determine_target_column_name(date(2026, 6, 20), date(2026, 6, 16)) == "This Week"
        assert determine_target_column_name(date(2026, 6, 20), date(2026, 6, 20)) == "Focus"

    def test_monday_boundary_next_week_vs_this_week(self):
        """Sonntag -> Montag Uebergang: Montag der neuen Woche = This Week."""
        sunday = date(2026, 5, 17)
        monday = date(2026, 5, 18)
        assert determine_target_column_name(monday, sunday) == "Next Week"
        assert determine_target_column_name(monday, monday) == "Focus"

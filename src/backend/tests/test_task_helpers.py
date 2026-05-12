"""Tests fuer isolierte Helper-Funktionen aus dem Task-Router und Recurring-Modul.

Prüft:
- _resolve_assignee_input: 'me' → UUID, 'agent' → 'agent', None → None
- _sanitize_text: XSS-Schutz via bleach (HTML-Tags entfernen)
- Cron-Expression-Validierung und Scheduling via croniter
"""

import uuid
from datetime import datetime, timezone

import pytest
from croniter import croniter

from app.routers.tasks import _resolve_assignee_input, _sanitize_text
from tests.conftest import FakeUser, OWNER_ID, MEMBER_ID


# ---------------------------------------------------------------------------
# _resolve_assignee_input
# ---------------------------------------------------------------------------

class TestResolveAssigneeInput:
    """Prüft die Assignee-Auflösung (me → UUID, agent, None)."""

    def test_me_resolves_to_user_id(self, owner_user):
        result = _resolve_assignee_input("me", owner_user)
        assert result == str(OWNER_ID)

    def test_me_resolves_to_member_id(self, member_user):
        result = _resolve_assignee_input("me", member_user)
        assert result == str(MEMBER_ID)

    def test_agent_passes_through(self, owner_user):
        result = _resolve_assignee_input("agent", owner_user)
        assert result == "agent"

    def test_none_returns_none(self, owner_user):
        result = _resolve_assignee_input(None, owner_user)
        assert result is None

    def test_uuid_string_passes_through(self, owner_user):
        """Explizite UUID wird unverändert durchgereicht."""
        some_id = str(uuid.uuid4())
        result = _resolve_assignee_input(some_id, owner_user)
        assert result == some_id

    def test_empty_string_passes_through(self, owner_user):
        result = _resolve_assignee_input("", owner_user)
        assert result == ""


# ---------------------------------------------------------------------------
# _sanitize_text
# ---------------------------------------------------------------------------

class TestSanitizeText:
    """Prüft XSS-Schutz durch HTML-Tag-Entfernung."""

    def test_script_tag_stripped(self):
        result = _sanitize_text("<script>alert('xss')</script>Hello")
        assert "<script>" not in result
        assert "</script>" not in result
        assert "Hello" in result

    def test_plain_text_unchanged(self):
        text = "Normaler Text ohne HTML"
        assert _sanitize_text(text) == text

    def test_none_returns_none(self):
        assert _sanitize_text(None) is None

    def test_html_tags_stripped(self):
        result = _sanitize_text("<b>Fett</b> und <i>kursiv</i>")
        assert "<b>" not in result
        assert "<i>" not in result
        assert "Fett" in result
        assert "kursiv" in result

    def test_nested_tags_stripped(self):
        result = _sanitize_text("<div><p>Paragraph</p></div>")
        assert "<div>" not in result
        assert "<p>" not in result
        assert "Paragraph" in result

    def test_img_tag_stripped(self):
        result = _sanitize_text('<img src="x" onerror="alert(1)">')
        assert "<img" not in result
        assert "onerror" not in result

    def test_link_tag_stripped(self):
        result = _sanitize_text('<a href="https://evil.com">Klick</a>')
        assert "<a" not in result
        assert "Klick" in result

    def test_umlauts_preserved(self):
        text = "Prüfung der Lösung für Übungen"
        assert _sanitize_text(text) == text

    def test_empty_string(self):
        assert _sanitize_text("") == ""

    def test_style_tag_stripped(self):
        result = _sanitize_text("<style>body{display:none}</style>Sichtbar")
        assert "<style>" not in result
        assert "Sichtbar" in result


# ---------------------------------------------------------------------------
# Cron-Validierung (croniter) — isolierte Logik aus recurring.py
# ---------------------------------------------------------------------------

class TestCronValidation:
    """Prüft Cron-Expression-Parsing wie es im Recurring-Scheduler verwendet wird."""

    @pytest.mark.parametrize("expression", [
        "0 9 * * 1",       # Montag 09:00
        "0 8 * * 1-5",     # Werktags 08:00
        "30 14 1 * *",     # Monatlich am 1. um 14:30
        "0 0 * * *",       # Täglich Mitternacht
        "*/15 * * * *",    # Alle 15 Minuten
    ])
    def test_valid_cron_expressions(self, expression):
        assert croniter.is_valid(expression)

    @pytest.mark.parametrize("expression", [
        "",
        "invalid",
        "60 * * * *",       # Minute > 59
        "* 25 * * *",       # Stunde > 23
        "* * 32 * *",       # Tag > 31
        "not a cron",
    ])
    def test_invalid_cron_expressions(self, expression):
        assert not croniter.is_valid(expression)

    def test_next_occurrence_calculation(self):
        """Nächster Lauf nach einem Zeitpunkt wird korrekt berechnet."""
        base = datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc)  # Montag
        cron = croniter("0 9 * * 1", base)  # Montags 09:00
        next_run = cron.get_next(datetime)

        assert next_run.hour == 9
        assert next_run.minute == 0
        assert next_run.weekday() == 0  # Montag

    def test_daily_cron_next_day(self):
        """Tägliche Cron-Expression berechnet nächsten Tag."""
        base = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
        cron = croniter("0 9 * * *", base)  # Täglich 09:00
        next_run = cron.get_next(datetime)

        assert next_run.day == 13
        assert next_run.hour == 9

    def test_monthly_cron(self):
        """Monatliche Cron-Expression am 1. des Monats."""
        base = datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc)
        cron = croniter("0 8 1 * *", base)  # Am 1. um 08:00
        next_run = cron.get_next(datetime)

        assert next_run.month == 6
        assert next_run.day == 1
        assert next_run.hour == 8

    def test_weekday_only_cron(self):
        """Werktags-Cron überspringt Wochenende."""
        base = datetime(2026, 5, 8, 18, 0, tzinfo=timezone.utc)  # Freitag Abend
        cron = croniter("0 9 * * 1-5", base)
        next_run = cron.get_next(datetime)

        assert next_run.weekday() == 0  # Montag
        assert next_run.day == 11

    def test_timezone_naive_result(self):
        """croniter gibt standardmässig timezone-naive Datetimes zurück."""
        base = datetime(2026, 5, 12, 0, 0)
        cron = croniter("0 9 * * *", base)
        next_run = cron.get_next(datetime)
        assert next_run.tzinfo is None

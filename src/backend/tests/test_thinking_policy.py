"""Tests für die Thinking-Policy (_thinking_disabled).

Prüft, dass der Config-Schalter ``triage_disable_thinking`` nur für Triage-
Jobtypen greift und Nicht-Triage-Jobs unberührt lässt. ``get_settings`` ist
gemockt, kein DB/Netz nötig.
"""

from types import SimpleNamespace
from unittest.mock import patch

import app.services.hermes_worker as hw


def _settings(disable_thinking=False):
    return SimpleNamespace(triage_disable_thinking=disable_thinking)


def test_thinking_on_by_default_for_triage():
    with patch.object(hw, "get_settings", return_value=_settings(False)):
        assert hw._thinking_disabled("email_triage", None) is False
        assert hw._thinking_disabled("chat_triage", None) is False


def test_config_flag_disables_thinking_for_triage():
    with patch.object(hw, "get_settings", return_value=_settings(True)):
        assert hw._thinking_disabled("email_triage", None) is True
        assert hw._thinking_disabled("chat_triage", None) is True


def test_config_flag_does_not_affect_non_triage_jobs():
    # Der Triage-Schalter darf andere Jobtypen (z. B. Draft/Chat-Agent) nicht anfassen.
    with patch.object(hw, "get_settings", return_value=_settings(True)):
        assert hw._thinking_disabled("send_email", None) is False
        assert hw._thinking_disabled("generic", None) is False
        assert hw._thinking_disabled(None, None) is False


def test_static_disabled_list_still_wins():
    # Die mechanische Liste bleibt unabhaengig vom Config-Schalter wirksam.
    with patch.object(hw, "_THINKING_DISABLED_JOB_TYPES", {"some_mechanical_job"}), \
         patch.object(hw, "get_settings", return_value=_settings(False)):
        assert hw._thinking_disabled("some_mechanical_job", None) is True

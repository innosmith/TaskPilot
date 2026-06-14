"""Unit-Tests fuer reine Lern-Signal-Funktionen.

- ``extract_teach_intent``: erkennt "merk dir ..."-Lehr-Absichten im Chat.
- ``_compute_self_grade``: bewertet deterministisch, ob Pflicht-Kontexte geladen
  wurden.
"""

from app.services.learning import extract_teach_intent
from app.services.hermes_worker import _compute_self_grade


class TestExtractTeachIntent:
    def test_merk_dir(self):
        lesson = extract_teach_intent(
            "Merk dir: Rechnungen von Treuhand immer als Finanzen taggen."
        )
        assert lesson == "Rechnungen von Treuhand immer als Finanzen taggen"

    def test_merke_dir_bitte(self):
        lesson = extract_teach_intent(
            "Merke dir bitte, dass BFH-Mails immer hohe Prioritaet haben"
        )
        assert lesson is not None
        assert "BFH" in lesson

    def test_kuenftig_trigger(self):
        lesson = extract_teach_intent(
            "Künftig sollst du Newsletter sofort archivieren"
        )
        assert lesson is not None
        assert "Newsletter" in lesson

    def test_no_trigger_returns_none(self):
        assert extract_teach_intent("Wie ist der Stand beim Projekt X?") is None

    def test_empty_returns_none(self):
        assert extract_teach_intent("") is None
        assert extract_teach_intent("   ") is None

    def test_trigger_with_short_content_falls_back_to_full(self):
        # Trigger erkannt, aber Rest zu kurz (<4) -> ganze Nachricht als Fallback.
        msg = "Merk dir das"
        assert extract_teach_intent(msg) == msg


class TestComputeSelfGrade:
    def test_full_context_loaded_scores_one(self):
        grade = _compute_self_grade(
            meta={"conversation_id": "conv-1"},
            result_meta={"draft_id": "draft-1"},
            tools_used=[
                "get_thread",
                "search_sender_history",
                "get_sender_profile",
                "search_my_replies",
            ],
        )
        assert grade["score"] == 1.0
        assert grade["missing"] == []

    def test_missing_profile_lowers_score(self):
        grade = _compute_self_grade(
            meta={},
            result_meta={},
            tools_used=["search_sender_history"],
        )
        # Nur 2 Checks (kein Thread, kein Draft); profile fehlt.
        assert "sender_profile_loaded" in grade["missing"]
        assert grade["score"] == 0.5

    def test_no_draft_skips_style_anchor_check(self):
        grade = _compute_self_grade(
            meta={},
            result_meta={},
            tools_used=["search_sender_history", "get_sender_profile"],
        )
        assert "style_anchor_used" not in grade["checks"]
        assert grade["score"] == 1.0

    def test_substring_match_handles_mcp_prefix(self):
        grade = _compute_self_grade(
            meta={},
            result_meta={},
            tools_used=["taskpilot.get_sender_profile", "graph.search_sender_history"],
        )
        assert grade["checks"]["sender_profile_loaded"] is True
        assert grade["checks"]["sender_history_loaded"] is True

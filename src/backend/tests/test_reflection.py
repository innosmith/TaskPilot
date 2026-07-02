"""Unit-Tests fuer die deterministische Mustererkennung des Reflexions-Jobs.

Testet ``_build_proposals`` rein (ohne DB): aus Korrektursignalen werden bei
wiederkehrenden Mustern Regel-Vorschlaege abgeleitet.
"""

from types import SimpleNamespace

from app.services.reflection import _build_proposals


def _fb(feedback_type, *, sender=None, original=None, corrected=None):
    return SimpleNamespace(
        feedback_type=feedback_type,
        sender_email=sender,
        original=original or {},
        corrected=corrected or {},
    )


class TestBuildProposals:
    def test_recurring_reclass_creates_triage_rule(self):
        fb = [
            _fb("triage_reclass", sender="kunde@firma.ch",
                original={"triage_class": "fyi"}, corrected={"triage_class": "task"}),
            _fb("triage_reclass", sender="Kunde@Firma.ch",
                original={"triage_class": "fyi"}, corrected={"triage_class": "task"}),
        ]
        proposals = _build_proposals(fb, min_occurrences=2)
        assert len(proposals) == 1
        scope, text, evidence, hint = proposals[0]
        assert scope == "triage"
        assert "task" in text
        assert evidence["count"] == 2
        assert evidence["to_class"] == "task"
        assert hint == "L1"

    def test_below_threshold_no_proposal(self):
        fb = [
            _fb("triage_reclass", sender="a@b.ch",
                original={"triage_class": "fyi"}, corrected={"triage_class": "task"}),
        ]
        assert _build_proposals(fb, min_occurrences=2) == []

    def test_same_class_is_ignored(self):
        fb = [
            _fb("triage_reclass", sender="a@b.ch",
                original={"triage_class": "task"}, corrected={"triage_class": "task"}),
            _fb("triage_reclass", sender="a@b.ch",
                original={"triage_class": "task"}, corrected={"triage_class": "task"}),
        ]
        assert _build_proposals(fb, min_occurrences=2) == []

    def test_recurring_draft_edits_create_draft_rule(self):
        fb = [
            _fb("draft_edit", sender="vip@kunde.ch"),
            _fb("draft_edit", sender="vip@kunde.ch"),
            _fb("draft_edit", sender="vip@kunde.ch"),
        ]
        proposals = _build_proposals(fb, min_occurrences=2)
        assert len(proposals) == 1
        scope, text, evidence, _hint = proposals[0]
        assert scope == "draft"
        assert "search_my_replies" in text
        assert evidence["count"] == 3

    def test_case_insensitive_sender_grouping(self):
        fb = [
            _fb("draft_edit", sender="X@Y.ch"),
            _fb("draft_edit", sender="x@y.ch"),
        ]
        proposals = _build_proposals(fb, min_occurrences=2)
        assert len(proposals) == 1
        assert proposals[0][2]["sender"] == "x@y.ch"

    def test_feedback_without_sender_ignored(self):
        fb = [
            _fb("draft_edit", sender=None),
            _fb("draft_edit", sender=None),
        ]
        assert _build_proposals(fb, min_occurrences=2) == []

    def test_discarded_task_suggestions_create_triage_rule(self):
        # Haeufigstes Realbetrieb-Signal: wiederholt verworfene Task-Vorschlaege
        # desselben Absenders -> zurueckhaltende Triage-Leitregel.
        fb = [
            _fb("task_deleted", sender="alerts@system.ch"),
            _fb("task_deleted", sender="alerts@system.ch"),
            _fb("rejected", sender="alerts@system.ch"),
        ]
        proposals = _build_proposals(fb, min_occurrences=3)
        assert len(proposals) == 1
        scope, text, evidence, hint = proposals[0]
        assert scope == "triage"
        assert "fyi" in text.lower()
        assert evidence["signal"] == "discarded_suggestions"
        assert evidence["count"] == 3
        assert hint == "L1"

    def test_discarded_below_threshold_no_proposal(self):
        fb = [
            _fb("task_deleted", sender="alerts@system.ch"),
            _fb("task_deleted", sender="alerts@system.ch"),
        ]
        assert _build_proposals(fb, min_occurrences=3) == []

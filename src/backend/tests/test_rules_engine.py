"""Tests für die Regel-Engine-Logik (app.services.rules) + API-Validierung.

Reine Logik -- kein DB/Graph nötig. Prüft, dass Bedingungen korrekt gegen
E-Mail-Daten ausgewertet werden und die API-Validierung ungültige Bausteine
ablehnt.
"""

import pytest
from fastapi import HTTPException

from app.services.rules import (
    evaluate_condition,
    evaluate_conditions,
    normalize_conditions,
)


def _email(address: str = "kunde@example.ch", subject: str = "Offerte 2026") -> dict:
    return {
        "from": {"emailAddress": {"address": address, "name": "Kundin"}},
        "subject": subject,
    }


class TestEvaluateCondition:
    def test_sender_equals_match(self):
        cond = {"field": "sender", "op": "equals", "value": "Kunde@Example.ch"}
        assert evaluate_condition(cond, _email()) is True

    def test_sender_equals_no_match(self):
        cond = {"field": "sender", "op": "equals", "value": "andere@example.ch"}
        assert evaluate_condition(cond, _email()) is False

    def test_domain_equals_match(self):
        cond = {"field": "domain", "op": "equals", "value": "example.ch"}
        assert evaluate_condition(cond, _email()) is True

    def test_subject_contains_match(self):
        cond = {"field": "subject", "op": "contains", "value": "offerte"}
        assert evaluate_condition(cond, _email()) is True

    def test_subject_contains_no_match(self):
        cond = {"field": "subject", "op": "contains", "value": "rechnung"}
        assert evaluate_condition(cond, _email()) is False

    def test_unknown_field_is_false(self):
        cond = {"field": "body", "op": "contains", "value": "x"}
        assert evaluate_condition(cond, _email()) is False

    def test_unknown_op_is_false(self):
        cond = {"field": "sender", "op": "regex", "value": "x"}
        assert evaluate_condition(cond, _email()) is False

    def test_empty_value_is_false(self):
        cond = {"field": "sender", "op": "equals", "value": "   "}
        assert evaluate_condition(cond, _email()) is False


class TestEvaluateConditions:
    def test_all_match_is_true(self):
        conds = [
            {"field": "domain", "op": "equals", "value": "example.ch"},
            {"field": "subject", "op": "contains", "value": "offerte"},
        ]
        assert evaluate_conditions(conds, _email()) is True

    def test_one_fails_is_false(self):
        conds = [
            {"field": "domain", "op": "equals", "value": "example.ch"},
            {"field": "subject", "op": "contains", "value": "rechnung"},
        ]
        assert evaluate_conditions(conds, _email()) is False

    def test_empty_conditions_is_false(self):
        # Eine Regel ohne Bedingung darf nie greifen (kein Blankoscheck).
        assert evaluate_conditions([], _email()) is False
        assert evaluate_conditions(None, _email()) is False


class TestNormalizeConditions:
    def test_strips_value_and_keeps_keys(self):
        out = normalize_conditions([{"field": "sender", "op": "equals", "value": "  a@b.ch "}])
        assert out == [{"field": "sender", "op": "equals", "value": "a@b.ch"}]

    def test_ignores_non_dicts(self):
        assert normalize_conditions(["x", 1, None]) == []
        assert normalize_conditions("nope") == []


class TestValidateRulePayload:
    def _call(self, **kwargs):
        from app.routers.intelligence import RuleAction, RuleCondition, _validate_rule_payload

        defaults = dict(
            rule_type="llm",
            scope="triage",
            status="active",
            conditions=[],
            action=None,
        )
        defaults.update(kwargs)
        # Bedingungen/Action als Pydantic-Objekte aufbereiten.
        defaults["conditions"] = [RuleCondition(**c) if isinstance(c, dict) else c for c in defaults["conditions"]]
        if isinstance(defaults["action"], dict):
            defaults["action"] = RuleAction(**defaults["action"])
        _validate_rule_payload(
            defaults["rule_type"], defaults["scope"], defaults["status"],
            defaults["conditions"], defaults["action"],
        )

    def test_valid_llm_rule_passes(self):
        self._call(rule_type="llm", scope="chat")

    def test_invalid_scope_rejected(self):
        with pytest.raises(HTTPException):
            self._call(scope="nonsense")

    def test_invalid_rule_type_rejected(self):
        with pytest.raises(HTTPException):
            self._call(rule_type="magic")

    def test_deterministic_without_conditions_rejected(self):
        with pytest.raises(HTTPException):
            self._call(rule_type="deterministic", conditions=[])

    def test_deterministic_with_valid_condition_passes(self):
        self._call(
            rule_type="deterministic",
            conditions=[{"field": "domain", "op": "equals", "value": "example.ch"}],
            action={"triage_class": "fyi", "category": "Kalender", "folder": "Kalender"},
        )

    def test_deterministic_invalid_action_class_rejected(self):
        with pytest.raises(HTTPException):
            self._call(
                rule_type="deterministic",
                conditions=[{"field": "domain", "op": "equals", "value": "example.ch"}],
                action={"triage_class": "auto_reply"},
            )

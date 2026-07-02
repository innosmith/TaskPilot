"""Tests für die deterministische Regel-Engine (apply_deterministic_rules).

Kein LLM/keine echte DB: DB-Session und Graph-Client sind gemockt. Geprüft wird
die *Entscheidung* (greift eine Regel?) und die ausgeführte Aktion (Kategorie +
Move), analog zur Meeting-Override.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.triage import apply_deterministic_rules


class _FakeDB:
    def __init__(self):
        self.add = MagicMock()
        self.flush = AsyncMock()
        self.execute = AsyncMock()


def _rule(conditions, action, rule_text="Testregel"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        rule_type="deterministic",
        status="active",
        rule_text=rule_text,
        match_conditions=conditions,
        action=action,
        priority=100,
        applied_count=0,
    )


def _email(address="kunde@example.ch", subject="Newsletter"):
    return {
        "id": "MID-1",
        "from": {"emailAddress": {"address": address, "name": "Kundin"}},
        "subject": subject,
        "receivedDateTime": "2026-06-24T10:00:00Z",
        "inferenceClassification": "focused",
        "conversationId": "C1",
    }


@pytest.mark.asyncio
async def test_matching_rule_applies_action():
    db = _FakeDB()
    client = MagicMock()
    client.set_categories = AsyncMock()
    client.move_to_folder = AsyncMock()
    rule = _rule(
        [{"field": "domain", "op": "equals", "value": "example.ch"}],
        {"triage_class": "fyi", "category": "Newsletter", "folder": "Newsletter"},
    )

    handled = await apply_deterministic_rules(db, client, _email(), [rule])

    assert handled is True
    db.add.assert_called_once()
    client.set_categories.assert_awaited_once_with("MID-1", ["Newsletter"])
    client.move_to_folder.assert_awaited_once_with("MID-1", "Newsletter")
    # applied_count-Update wird abgesetzt.
    db.execute.assert_awaited()


@pytest.mark.asyncio
async def test_non_matching_rule_does_not_apply():
    db = _FakeDB()
    client = MagicMock()
    client.set_categories = AsyncMock()
    client.move_to_folder = AsyncMock()
    rule = _rule(
        [{"field": "domain", "op": "equals", "value": "andere.ch"}],
        {"triage_class": "fyi", "category": "Newsletter", "folder": "Newsletter"},
    )

    handled = await apply_deterministic_rules(db, client, _email(), [rule])

    assert handled is False
    db.add.assert_not_called()
    client.set_categories.assert_not_called()
    client.move_to_folder.assert_not_called()


@pytest.mark.asyncio
async def test_first_matching_rule_wins():
    db = _FakeDB()
    client = MagicMock()
    client.set_categories = AsyncMock()
    client.move_to_folder = AsyncMock()
    miss = _rule(
        [{"field": "subject", "op": "contains", "value": "rechnung"}],
        {"triage_class": "fyi", "category": "Finanzen", "folder": "Finanzen"},
    )
    hit = _rule(
        [{"field": "subject", "op": "contains", "value": "newsletter"}],
        {"triage_class": "fyi", "category": "Newsletter", "folder": "Newsletter"},
    )

    handled = await apply_deterministic_rules(db, client, _email(), [miss, hit])

    assert handled is True
    client.set_categories.assert_awaited_once_with("MID-1", ["Newsletter"])


@pytest.mark.asyncio
async def test_no_rules_returns_false():
    db = _FakeDB()
    client = MagicMock()
    handled = await apply_deterministic_rules(db, client, _email(), [])
    assert handled is False

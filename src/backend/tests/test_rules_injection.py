"""Tests für die kontextbewusste Regel-Injektion (_build_rules_block).

Kein echtes DB: ``async_session`` ist gemockt. Geprüft werden Formatierung,
Leerfall und das Scope-Alias-Mapping (email-triage -> triage).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.hermes_worker as hw


class _FakeDB:
    def __init__(self, rules):
        self._rules = rules

    async def execute(self, *args, **kwargs):
        res = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = self._rules
        res.scalars.return_value = scalars
        return res


class _FakeSession:
    def __init__(self, rules):
        self._db = _FakeDB(rules)

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *args):
        return False


def _session_factory(rules):
    return lambda: _FakeSession(rules)


@pytest.mark.asyncio
async def test_block_lists_rules():
    rules = [
        SimpleNamespace(scope="triage", rule_text="Terminzusagen sind fyi"),
        SimpleNamespace(scope="general", rule_text="Immer höflich bleiben"),
    ]
    with patch.object(hw, "async_session", _session_factory(rules)):
        block = await hw._build_rules_block("triage")
    assert "Terminzusagen sind fyi" in block
    assert "[general]" in block
    assert "AKTIVE GELERNTE REGELN" in block


@pytest.mark.asyncio
async def test_empty_rules_returns_empty_string():
    with patch.object(hw, "async_session", _session_factory([])):
        block = await hw._build_rules_block("chat")
    assert block == ""


def test_scope_alias_mapping():
    assert hw._SCOPE_CONTEXT_ALIASES.get("email-triage") == "triage"
    assert hw._SCOPE_CONTEXT_ALIASES.get("email-style") == "draft"

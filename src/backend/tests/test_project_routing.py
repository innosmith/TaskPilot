"""Tests für das gelernte Projekt-Routing (_build_project_routing_hint).

Kein echtes DB: ``async_session`` und ``get_settings`` sind gemockt. Geprüft
werden Aggregation der ``task_moved``-Signale pro Absender, die Schwelle
(``agent_reflection_min_occurrences``) und die Prompt-Injektion.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.hermes_worker as hw


class _FakeDB:
    def __init__(self, corrected_rows, project):
        self._rows = corrected_rows
        self._project = project

    async def execute(self, *args, **kwargs):
        res = MagicMock()
        res.all.return_value = [(c,) for c in self._rows]
        return res

    async def get(self, model, pk):
        return self._project


class _FakeSession:
    def __init__(self, corrected_rows, project):
        self._db = _FakeDB(corrected_rows, project)

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *args):
        return False


def _session_factory(corrected_rows, project):
    return lambda: _FakeSession(corrected_rows, project)


def _fake_settings(min_occurrences=2):
    return SimpleNamespace(agent_reflection_min_occurrences=min_occurrences)


@pytest.mark.asyncio
async def test_hint_returned_above_threshold():
    pid = str(uuid.uuid4())
    rows = [{"project_id": pid}, {"project_id": pid}, {"project_id": pid}]
    project = SimpleNamespace(name="Kunde ACME", status="active")
    with patch.object(hw, "async_session", _session_factory(rows, project)), \
         patch.object(hw, "get_settings", return_value=_fake_settings(2)):
        hint = await hw._build_project_routing_hint("kontakt@acme.ch")
    assert "GELERNTES PROJEKT-ROUTING" in hint
    assert "Kunde ACME" in hint
    assert "kontakt@acme.ch" in hint
    assert "3x" in hint


@pytest.mark.asyncio
async def test_no_hint_below_threshold():
    pid = str(uuid.uuid4())
    rows = [{"project_id": pid}]  # nur 1 Verschiebung < Schwelle 2
    project = SimpleNamespace(name="Kunde ACME", status="active")
    with patch.object(hw, "async_session", _session_factory(rows, project)), \
         patch.object(hw, "get_settings", return_value=_fake_settings(2)):
        hint = await hw._build_project_routing_hint("kontakt@acme.ch")
    assert hint == ""


@pytest.mark.asyncio
async def test_picks_most_common_target():
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    # A: 3x, B: 1x -> A gewinnt
    rows = [
        {"project_id": pid_a}, {"project_id": pid_b},
        {"project_id": pid_a}, {"project_id": pid_a},
    ]

    captured = {}

    class _DB(_FakeDB):
        async def get(self, model, pk):
            captured["pk"] = str(pk)
            return SimpleNamespace(name="Projekt A", status="active")

    class _Sess(_FakeSession):
        def __init__(self, rows, project):
            self._db = _DB(rows, project)

    with patch.object(hw, "async_session", lambda: _Sess(rows, None)), \
         patch.object(hw, "get_settings", return_value=_fake_settings(2)):
        hint = await hw._build_project_routing_hint("kontakt@acme.ch")
    assert captured["pk"] == pid_a
    assert "Projekt A" in hint


@pytest.mark.asyncio
async def test_empty_for_missing_address():
    hint = await hw._build_project_routing_hint("")
    assert hint == ""


@pytest.mark.asyncio
async def test_no_hint_for_archived_project():
    pid = str(uuid.uuid4())
    rows = [{"project_id": pid}, {"project_id": pid}]
    project = SimpleNamespace(name="Altprojekt", status="archived")
    with patch.object(hw, "async_session", _session_factory(rows, project)), \
         patch.object(hw, "get_settings", return_value=_fake_settings(2)):
        hint = await hw._build_project_routing_hint("kontakt@acme.ch")
    assert hint == ""


@pytest.mark.asyncio
async def test_hint_injected_into_triage_prompt():
    """Der Routing-Hinweis wird in den Triage-Prompt eingespeist."""
    job = SimpleNamespace(
        id=uuid.uuid4(),
        metadata_json={
            "email_message_id": "AAMk1",
            "subject": "Angebot",
            "from_address": "kontakt@acme.ch",
            "from_name": "ACME",
            "conversation_id": "",
            "body_preview": "Test",
            "inference_classification": "focused",
            "recipient_type": "to",
        },
    )
    with patch.object(hw, "_load_projects_context", new=AsyncMock(return_value="## VERFÜGBARE PROJEKTE")), \
         patch.object(hw, "_load_style_profile", return_value="stil"), \
         patch.object(hw, "_load_triage_skill", return_value="skill"), \
         patch.object(hw, "_triage_skill_available", return_value=True), \
         patch.object(hw, "_style_skill_available", return_value=True), \
         patch.object(hw, "_build_project_routing_hint", new=AsyncMock(return_value="\n---\n\n## GELERNTES PROJEKT-ROUTING (weicher Hinweis)\nROUTING_SENTINEL\n")):
        prompt = await hw._build_triage_prompt(job)
    assert "ROUTING_SENTINEL" in prompt

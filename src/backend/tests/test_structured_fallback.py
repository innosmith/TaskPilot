"""Tests für den tool-freien Structured-Output-Rettungspfad (_structured_triage_reask).

Kein Agenten-Loop, kein echtes Ollama: der HTTP-Call ist via ``respx`` gemockt,
``get_settings`` liefert ein Fake-Setting. Geprüft werden Aktivierungs-Flag,
Cloud-Ausschluss, erfolgreiche Rettung und Ablehnung ungültiger Klassen.
"""

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
import respx

import app.services.hermes_worker as hw

_OLLAMA_URL = "http://ollama:11434/v1/chat/completions"


def _settings(enabled=True, model="ollama/qwen3.6:latest", base="http://ollama:11434"):
    return SimpleNamespace(
        triage_structured_fallback=enabled,
        triage_model=model,
        ollama_base_url=base,
    )


@pytest.mark.asyncio
@respx.mock
async def test_reask_recovers_classification():
    route = respx.post(_OLLAMA_URL).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"triage_class":"fyi","label":"Info","reply_expected":false}'}}]},
        )
    )
    with patch.object(hw, "get_settings", return_value=_settings(True)):
        parsed = await hw._structured_triage_reask(
            {"subject": "Terminzusage", "from_address": "a@b.ch", "body_preview": "angenommen"},
            "Der Agent analysierte ...",
        )
    assert route.called
    assert parsed is not None
    assert parsed["triage_class"] == "fyi"


@pytest.mark.asyncio
async def test_reask_disabled_returns_none():
    with patch.object(hw, "get_settings", return_value=_settings(enabled=False)):
        parsed = await hw._structured_triage_reask({"subject": "x"}, "y")
    assert parsed is None


@pytest.mark.asyncio
async def test_reask_skips_cloud_model():
    with patch.object(hw, "get_settings", return_value=_settings(True, model="openai/gpt-5")):
        parsed = await hw._structured_triage_reask({"subject": "x"}, "y")
    assert parsed is None


@pytest.mark.asyncio
@respx.mock
async def test_reask_rejects_invalid_class():
    respx.post(_OLLAMA_URL).mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": '{"triage_class":"bogus"}'}}]}
        )
    )
    with patch.object(hw, "get_settings", return_value=_settings(True)):
        parsed = await hw._structured_triage_reask({"subject": "x"}, "y")
    assert parsed is None


@pytest.mark.asyncio
@respx.mock
async def test_reask_handles_http_error_gracefully():
    respx.post(_OLLAMA_URL).mock(return_value=httpx.Response(500))
    with patch.object(hw, "get_settings", return_value=_settings(True)):
        parsed = await hw._structured_triage_reask({"subject": "x"}, "y")
    assert parsed is None


@pytest.mark.asyncio
@respx.mock
async def test_reask_uses_json_schema_first():
    """Der erste Call nutzt schema-constrained Decoding (Best Practice)."""
    route = respx.post(_OLLAMA_URL).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"rationale":"info","triage_class":"fyi","reply_expected":false}'}}]},
        )
    )
    with patch.object(hw, "get_settings", return_value=_settings(True)):
        parsed = await hw._structured_triage_reask(
            {"subject": "Newsletter", "from_address": "a@b.ch", "body_preview": "..."},
            "Analyse ...",
        )
    assert parsed is not None and parsed["triage_class"] == "fyi"
    import json as _json
    sent = _json.loads(route.calls.last.request.content)
    assert sent["response_format"]["type"] == "json_schema"
    schema = sent["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["triage_class"]["enum"] == ["task", "auto_reply", "fyi"]
    # rationale steht als erstes Property ("reasoning before answer").
    assert list(schema["properties"].keys())[0] == "rationale"


@pytest.mark.asyncio
@respx.mock
async def test_reask_graceful_fallback_to_json_object():
    """Kann Ollama json_schema nicht (z.B. 400), faellt der Call auf json_object zurueck."""
    route = respx.post(_OLLAMA_URL).mock(
        side_effect=[
            httpx.Response(400, json={"error": "unsupported format"}),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"triage_class":"task","reply_expected":true}'}}]},
            ),
        ]
    )
    with patch.object(hw, "get_settings", return_value=_settings(True)):
        parsed = await hw._structured_triage_reask({"subject": "x", "from_address": "a@b.ch"}, "y")
    assert route.call_count == 2
    assert parsed is not None and parsed["triage_class"] == "task"
    import json as _json
    second = _json.loads(route.calls[1].request.content)
    assert second["response_format"] == {"type": "json_object"}

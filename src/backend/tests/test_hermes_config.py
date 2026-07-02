"""Tests für die generierte Hermes-Runtime-Config (build_config_dict).

Sichert die Governance-/Hardening-Entscheidungen ab: Skill-Writes gegated,
alle Auxiliary-Slots auf dem lokalen Ollama-Endpoint, Gateway-Curator aus.
Kein DB/Netz nötig -- build_config_dict liest nur Pydantic-Settings.
"""

import yaml

from app.services.hermes_config import build_config_dict

_AUX_SLOTS = (
    "compression", "vision", "web_extract", "background_review",
    "title_generation", "curator",
)


def test_skill_writes_are_gated():
    cfg = build_config_dict()
    assert cfg["skills"]["write_approval"] is True
    # Bestehende Einstellung bleibt erhalten.
    assert cfg["skills"]["creation_nudge_interval"] == 25


def test_all_auxiliary_slots_pinned_to_local():
    cfg = build_config_dict()
    aux = cfg["auxiliary"]
    for slot in _AUX_SLOTS:
        assert slot in aux, f"Aux-Slot fehlt: {slot}"
        assert aux[slot]["provider"] == "custom"
        assert aux[slot]["api_key"] == "ollama"
        assert aux[slot]["base_url"].endswith("/v1")
        assert aux[slot]["model"] and "ollama/" not in aux[slot]["model"]


def test_legacy_title_slot_removed():
    """Der fruehere Key 'title' war in Hermes 0.18 wirkungslos -- der korrekte
    Slot heisst 'title_generation'."""
    cfg = build_config_dict()
    assert "title" not in cfg["auxiliary"]
    assert "title_generation" in cfg["auxiliary"]


def test_web_backends_explicitly_pinned():
    """Suche via ddgs (anonym, gratis), Extraktion via Tavily (einziges
    Extract-Backend). Explizit statt kaskadenabhängig -- die Auto-Detect-
    Kaskade war zuvor auf ddgs (search-only) gefallen und web_extract
    damit funktionslos."""
    cfg = build_config_dict()
    assert cfg["web"]["search_backend"] == "ddgs"
    assert cfg["web"]["extract_backend"] == "tavily"


def test_taskpilot_mcp_env_without_tavily_key():
    """Das MCP-Tool mcp_taskpilot_web_search wurde entfernt (Redundanz zur
    Hermes-nativen Websuche + Doppel-Logging) -- der taskpilot-Server braucht
    den Tavily-Key nicht mehr."""
    cfg = build_config_dict()
    env = cfg["mcp_servers"]["taskpilot"]["env"]
    assert "TP_TAVILY_API_KEY" not in env


def test_populate_hermes_env_mirrors_tavily_key(monkeypatch):
    """Hermes' native Web-Tools lesen TAVILY_API_KEY UNpräfixiert -- ohne
    Spiegelung fällt die Backend-Kaskade auf ddgs zurück und web_extract
    ist funktionslos."""
    import asyncio
    import os

    from app.services.hermes_config import populate_hermes_env

    monkeypatch.setenv("TP_TAVILY_API_KEY", "tvly-test-dummy")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    asyncio.run(populate_hermes_env())
    assert os.environ.get("TAVILY_API_KEY") == "tvly-test-dummy"


def test_gateway_curator_defensively_disabled():
    cfg = build_config_dict()
    assert cfg["curator"]["enabled"] is False
    assert cfg["curator"]["prune_builtins"] is False
    assert cfg["curator"]["consolidate"] is False


def test_config_yaml_roundtrip_without_aliases():
    """Aux-Slots sind eigenstaendige Dicts -- yaml.safe_dump darf keine Anker
    (&id/*id) erzeugen, die manche Loader anders behandeln."""
    cfg = build_config_dict()
    dumped = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    assert "&id" not in dumped and " *id" not in dumped
    reloaded = yaml.safe_load(dumped)
    assert reloaded["skills"]["write_approval"] is True
    assert set(_AUX_SLOTS).issubset(reloaded["auxiliary"].keys())

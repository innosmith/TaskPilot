"""Tests für die generierte Hermes-Runtime-Config (build_config_dict).

Sichert die Governance-/Hardening-Entscheidungen ab: Skill-Writes gegated,
alle Auxiliary-Slots auf dem lokalen Ollama-Endpoint, Gateway-Curator aus.
Kein DB/Netz nötig -- build_config_dict liest nur Pydantic-Settings.
"""

import yaml

from app.services.hermes_config import build_config_dict

_AUX_SLOTS = ("compression", "vision", "background_review", "title", "curator")


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

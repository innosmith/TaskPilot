"""Gemeinsame Logik fuer die Regel-Engine (deterministische Overrides).

Wird sowohl von der API (Validierung beim Anlegen/Bearbeiten) als auch vom
Triage-Worker (Auswertung gegen eingehende E-Mails) genutzt -- damit Validierung
und Ausfuehrung garantiert dieselben Felder/Operatoren kennen.
"""
from __future__ import annotations

# Erlaubte Bausteine deterministischer Regeln.
RULE_FIELDS = ("sender", "domain", "subject")
RULE_OPS = ("equals", "contains")
RULE_SCOPES = ("triage", "draft", "task", "calendar", "general", "chat")
RULE_TYPES = ("llm", "deterministic")
RULE_STATUSES = ("proposed", "active", "rejected", "archived")
# Klassen, die eine deterministische Aktion setzen darf.
ACTION_TRIAGE_CLASSES = ("fyi", "task")


def _email_field_value(email_data: dict, field: str) -> str:
    """Liest den Vergleichswert eines Feldes aus den Graph-E-Mail-Daten (lowercase)."""
    from_info = (email_data.get("from") or {}).get("emailAddress") or {}
    address = (from_info.get("address") or "").lower()
    if field == "sender":
        return address
    if field == "domain":
        return address.split("@", 1)[1] if "@" in address else ""
    if field == "subject":
        return (email_data.get("subject") or "").lower()
    return ""


def evaluate_condition(condition: dict, email_data: dict) -> bool:
    """Wertet eine einzelne Bedingung ``{field, op, value}`` aus."""
    field = condition.get("field")
    op = condition.get("op")
    value = (condition.get("value") or "").strip().lower()
    if field not in RULE_FIELDS or op not in RULE_OPS or not value:
        return False
    field_value = _email_field_value(email_data, field)
    if not field_value:
        return False
    if op == "equals":
        return field_value == value
    if op == "contains":
        return value in field_value
    return False


def evaluate_conditions(conditions, email_data: dict) -> bool:
    """True, wenn ALLE Bedingungen zutreffen (AND). Ohne Bedingung: False.

    Eine deterministische Regel ohne Bedingung darf nie greifen -- das waere ein
    Blankoscheck auf jede E-Mail.
    """
    if not isinstance(conditions, (list, tuple)) or not conditions:
        return False
    return all(evaluate_condition(c, email_data) for c in conditions if isinstance(c, dict))


def normalize_conditions(conditions) -> list[dict]:
    """Bringt Bedingungen in eine saubere Liste ``[{field, op, value}]``."""
    if not isinstance(conditions, (list, tuple)):
        return []
    out: list[dict] = []
    for c in conditions:
        if not isinstance(c, dict):
            continue
        out.append({
            "field": c.get("field"),
            "op": c.get("op"),
            "value": (c.get("value") or "").strip(),
        })
    return out

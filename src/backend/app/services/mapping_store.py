"""In-Memory Mapping-Keys-Store für Anonymisierungs-Sessions.

Speichert Mapping-Keys (Fake -> Original) mit automatischem TTL-Ablauf.
Keys liegen ausschliesslich im RAM -- kein Disk, keine DB.

Sicherheitseigenschaften:
- Keys werden nie an das Frontend gesendet
- Frontend bekommt nur session_id + diff_pairs für die Darstellung
- Bei Backend-Neustart gehen alle Keys verloren (by design)
"""

import uuid

from cachetools import TTLCache

from app.config import get_settings


class _MappingEntry:
    __slots__ = ("mapping_keys", "diff_pairs")

    def __init__(self, mapping_keys: dict, diff_pairs: list[dict]):
        self.mapping_keys = mapping_keys
        self.diff_pairs = diff_pairs


_store: TTLCache | None = None


def _get_store() -> TTLCache:
    global _store
    if _store is None:
        settings = get_settings()
        _store = TTLCache(maxsize=1000, ttl=settings.mapping_keys_ttl_seconds)
    return _store


def store_mapping(mapping_keys: dict) -> tuple[str, list[dict]]:
    """Speichert Mapping-Keys und gibt session_id + diff_pairs zurück.

    Args:
        mapping_keys: Mapping-Daten vom anonymize()-Aufruf
            (Format: {session_id, mappings: {fake: original}, entity_types: {fake: type}})

    Returns:
        Tuple (session_id, diff_pairs) -- diff_pairs für Frontend-Anzeige
    """
    session_id = mapping_keys.get("session_id", str(uuid.uuid4()))
    mappings = mapping_keys.get("mappings", {})
    entity_types = mapping_keys.get("entity_types", {})

    diff_pairs = [
        {
            "original": original,
            "fake": fake,
            "entity_type": entity_types.get(fake, "UNKNOWN"),
        }
        for fake, original in mappings.items()
    ]

    entry = _MappingEntry(mapping_keys=mapping_keys, diff_pairs=diff_pairs)
    _get_store()[session_id] = entry

    return session_id, diff_pairs


def get_diff_pairs(session_id: str) -> list[dict] | None:
    """Gibt die Diff-Paare für eine Session zurück (für Frontend-Anzeige)."""
    entry = _get_store().get(session_id)
    return entry.diff_pairs if entry else None


def get_mapping_keys(session_id: str) -> dict | None:
    """Gibt die vollständigen Mapping-Keys zurück (für De-Anonymisierung)."""
    entry = _get_store().get(session_id)
    return entry.mapping_keys if entry else None


def export_mapping_keys(session_id: str) -> dict | None:
    """Gibt die Mapping-Keys als exportierbares Dict zurück (für Download)."""
    return get_mapping_keys(session_id)


def remove_mapping(session_id: str) -> bool:
    """Entfernt Mapping-Keys manuell (z.B. nach De-Anonymisierung)."""
    store = _get_store()
    if session_id in store:
        del store[session_id]
        return True
    return False

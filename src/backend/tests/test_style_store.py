"""Tests fuer den Style-Store (Few-Shot-Draft-Anker).

Prueft die reinen Filter/Extraktions-Helfer sowie das Hybrid-Retrieval mit
gemockten Embeddings und einer Fake-DB (ohne echte pgvector-Verbindung).
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.services import style_store as ss


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return list(self._rows)

    def __iter__(self):
        return iter([(r["graph_id"],) for r in self._rows])


class _FakeDB:
    """Gibt pro execute-Aufruf das naechste vorbereitete Ergebnis zurueck."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, *args, **kwargs):
        rows = self._results[self.calls]
        self.calls += 1
        return _FakeResult(rows)


class TestNoiseFilter:
    def test_forward_is_noise(self):
        assert ss._is_noise("WG: Info", "a" * 60, "a@b.ch") is True
        assert ss._is_noise("Fwd: Info", "a" * 60, "a@b.ch") is True

    def test_too_short_is_noise(self):
        assert ss._is_noise("Re: Angebot", "kurz", "a@b.ch") is True

    def test_missing_recipient_is_noise(self):
        assert ss._is_noise("Re: Angebot", "a" * 60, None) is True

    def test_valid_reply_is_kept(self):
        assert ss._is_noise("Re: Angebot", "a" * 60, "a@b.ch") is False


def test_primary_recipient_lowercased():
    msg = {"toRecipients": [{"emailAddress": {"address": "Max@Firma.CH"}}]}
    assert ss._primary_recipient(msg) == "max@firma.ch"
    assert ss._primary_recipient({"toRecipients": []}) is None


@pytest.mark.asyncio
async def test_find_style_anchors_hybrid_dedup_and_cap():
    db = _FakeDB([
        # 1) Kontakt-spezifische Abfrage
        [{"graph_id": "g1", "recipient": "a@b.ch", "subject": "S1", "body_text": "Hallo A"}],
        # 2) Semantische Abfrage (g1 doppelt -> muss dedupliziert werden)
        [
            {"graph_id": "g1", "recipient": "a@b.ch", "subject": "S1", "body_text": "Hallo A", "similarity": 0.9},
            {"graph_id": "g2", "recipient": "c@d.ch", "subject": "S2", "body_text": "Hallo C", "similarity": 0.8},
            {"graph_id": "g3", "recipient": "e@f.ch", "subject": "S3", "body_text": "Hallo E", "similarity": 0.7},
        ],
    ])
    with patch.object(ss, "embed_text", new=AsyncMock(return_value=[0.1] * 1024)), \
            patch.object(ss, "to_pgvector", lambda v: "[vec]"):
        out = await ss.find_style_anchors(db, query_text="q", recipient="a@b.ch", k=2)
    ids = [o["graph_id"] for o in out]
    assert ids[0] == "g1"          # Kontakt-spezifisch zuerst
    assert ids.count("g1") == 1    # dedupliziert
    assert len(out) == 2           # auf k begrenzt


@pytest.mark.asyncio
async def test_find_style_anchors_without_embedding_returns_recipient_only():
    db = _FakeDB([
        [{"graph_id": "g1", "recipient": "a@b.ch", "subject": "S", "body_text": "Hallo"}],
    ])
    with patch.object(ss, "embed_text", new=AsyncMock(return_value=None)):
        out = await ss.find_style_anchors(db, query_text="q", recipient="a@b.ch", k=3)
    assert [o["graph_id"] for o in out] == ["g1"]

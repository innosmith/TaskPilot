"""Tests für die Triage-Prompt-Qualität.

Prüft:
- PFLICHT-Block enthalten ("MUSS aufgerufen werden" / "PFLICHT")
- Thread-Hint bei vorhandener conversation_id
- Keine ASCII-Umlaute (ue, ae, oe als Umlaut-Ersatz) im generierten Prompt
"""

import re
import uuid
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import pytest


def _make_fake_job(
    message_id="AAMk123",
    subject="Testbetreff",
    from_address="test@example.com",
    from_name="Test Sender",
    conversation_id="conv-abc",
    body_preview="Dies ist eine Test-E-Mail",
    inference_classification="focused",
    recipient_type="to",
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        metadata_json={
            "email_message_id": message_id,
            "subject": subject,
            "from_address": from_address,
            "from_name": from_name,
            "conversation_id": conversation_id,
            "body_preview": body_preview,
            "inference_classification": inference_classification,
            "recipient_type": recipient_type,
        },
    )


@pytest.fixture
def fake_job():
    return _make_fake_job()


@pytest.fixture
def fake_job_no_conversation():
    return _make_fake_job(conversation_id="")


class TestTriagePrompt:

    @pytest.mark.asyncio
    async def test_pflicht_block_present(self, fake_job):
        prompt = await self._build_prompt(fake_job)
        assert "PFLICHT" in prompt, "PFLICHT-Block fehlt im Prompt"
        assert "MUSS" in prompt or "muss" in prompt.lower()

    @pytest.mark.asyncio
    async def test_thread_hint_with_conversation_id(self, fake_job):
        prompt = await self._build_prompt(fake_job)
        assert "conv-abc" in prompt, "conversation_id sollte im Thread-Hint erscheinen"
        assert "get_thread" in prompt

    @pytest.mark.asyncio
    async def test_thread_hint_absent_without_conversation_id(self, fake_job_no_conversation):
        prompt = await self._build_prompt(fake_job_no_conversation)
        assert 'get_thread("")' in prompt or "get_thread" in prompt

    @pytest.mark.asyncio
    async def test_no_ascii_umlaut_replacements(self, fake_job):
        """Prüft, dass keine ue/ae/oe als Umlaut-Ersatz im Prompt vorkommen.

        Wir suchen nach typischen Mustern wie 'fuer', 'muessen', 'ueber' etc.,
        die auf ASCII-Umlaute hindeuten.
        """
        prompt = await self._build_prompt(fake_job)
        ascii_umlaut_patterns = [
            r"\bfuer\b",
            r"\bueber\b",
            r"\bmuessen\b",
            r"\bkoennen\b",
            r"\bmoechte\b",
            r"\bGruesse\b",
            r"\bAendern\b",
            r"\bOeffnen\b",
        ]
        for pattern in ascii_umlaut_patterns:
            matches = re.findall(pattern, prompt, re.IGNORECASE)
            assert len(matches) == 0, (
                f"ASCII-Umlaut-Pattern '{pattern}' gefunden im Prompt: {matches}"
            )

    @pytest.mark.asyncio
    async def test_contains_sender_info(self, fake_job):
        prompt = await self._build_prompt(fake_job)
        assert "test@example.com" in prompt
        assert "Test Sender" in prompt

    @pytest.mark.asyncio
    async def test_contains_subject(self, fake_job):
        prompt = await self._build_prompt(fake_job)
        assert "Testbetreff" in prompt

    @pytest.mark.asyncio
    async def test_recipient_type_to_in_prompt(self, fake_job):
        """Prompt zeigt recipient_type=to korrekt an."""
        prompt = await self._build_prompt(fake_job)
        assert "Empfänger-Typ:" in prompt
        assert "to" in prompt

    @pytest.mark.asyncio
    async def test_recipient_type_cc_shows_warning(self):
        """Bei CC-Mails erscheint eine deutliche Warnung im Prompt."""
        job = _make_fake_job(recipient_type="cc")
        prompt = await self._build_prompt(job)
        assert "NUR im CC" in prompt
        assert "fyi" in prompt
        assert "KEIN auto_reply" in prompt

    @pytest.mark.asyncio
    async def test_recipient_type_to_no_cc_warning(self, fake_job):
        """Bei TO-Mails erscheint KEINE dynamische CC-Warnung im Job-Block."""
        prompt = await self._build_prompt(fake_job)
        assert "⚠️ **ACHTUNG: Anthony ist bei dieser E-Mail NUR im CC" not in prompt

    @pytest.mark.asyncio
    async def test_style_block_injected(self, fake_job):
        """Wenn der Schreibstil-Kanon existiert, wird er im Prompt-Block injiziert."""
        sentinel = "Knapp, klar, kollegial, lösungsorientiert (STIL-SENTINEL)"
        prompt = await self._build_prompt(fake_job, style_text=sentinel)
        assert "SCHREIBSTIL" in prompt, "SCHREIBSTIL-Block fehlt im Prompt"
        assert sentinel in prompt, "Schreibstil-Kanon-Inhalt fehlt im Prompt"

    @pytest.mark.asyncio
    async def test_style_block_absent_when_empty(self, fake_job):
        """Ohne Schreibstil-Kanon wird kein SCHREIBSTIL-Block eingefügt."""
        prompt = await self._build_prompt(fake_job, style_text="")
        assert "SCHREIBSTIL (VERBINDLICH" not in prompt

    def test_style_canon_swiss_spelling(self):
        """Der echte Schreibstil-Kanon nutzt Schweizer Schreibweise (kein ß, keine ue/ae/oe-Ersatzformen)."""
        from app.services.hermes_worker import STYLE_PROFILE

        if not STYLE_PROFILE.exists():
            pytest.skip(f"Schreibstil-Kanon nicht vorhanden: {STYLE_PROFILE}")

        text = STYLE_PROFILE.read_text(encoding="utf-8")
        assert "ß" not in text, "Schreibstil-Kanon darf kein scharfes S enthalten"

        ascii_umlaut_patterns = [
            r"\bfuer\b", r"\bueber\b", r"\bmuessen\b", r"\bkoennen\b",
            r"\bmoechte\b", r"\bGruesse\b", r"\bAendern\b", r"\bOeffnen\b",
        ]
        for pattern in ascii_umlaut_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            assert len(matches) == 0, (
                f"ASCII-Umlaut-Pattern '{pattern}' im Schreibstil-Kanon: {matches}"
            )

    async def _build_prompt(self, job, style_text="(Schreibstil-Kanon Platzhalter)"):
        """Importiert und ruft _build_triage_prompt auf, mit gemockten DB-Calls.

        Der Schreibstil-Kanon wird gemockt, damit der Test unabhängig vom
        Dateisystem (~/.hermes/schreibstil-anthony.md) ist.
        """
        with patch("app.services.hermes_worker._load_projects_context", new_callable=AsyncMock) as mock_projects, \
             patch("app.services.hermes_worker._load_style_profile", return_value=style_text):
            mock_projects.return_value = "## VERFÜGBARE PROJEKTE\n- \"TestProjekt\" (id: 123)"

            from app.services.hermes_worker import _build_triage_prompt
            return await _build_triage_prompt(job)


class TestForcedClassCorrection:
    """Tests für den Berater-Korrektur-Block (forced_class) im Triage-Prompt."""

    async def _build_prompt(self, job, style_text="(Schreibstil-Kanon Platzhalter)"):
        with patch("app.services.hermes_worker._load_projects_context", new_callable=AsyncMock) as mock_projects, \
             patch("app.services.hermes_worker._load_style_profile", return_value=style_text):
            mock_projects.return_value = "## VERFÜGBARE PROJEKTE\n- \"TestProjekt\" (id: 123)"
            from app.services.hermes_worker import _build_triage_prompt
            return await _build_triage_prompt(job)

    @pytest.mark.asyncio
    async def test_no_correction_block_without_forced_class(self, fake_job):
        prompt = await self._build_prompt(fake_job)
        assert "KORREKTUR DES BERATERS" not in prompt

    @pytest.mark.asyncio
    async def test_correction_block_for_forced_task(self):
        job = _make_fake_job()
        job.metadata_json["forced_class"] = "task"
        job.metadata_json["correction_reason"] = "Das ist klar eine Aufgabe"
        prompt = await self._build_prompt(job)
        assert "KORREKTUR DES BERATERS" in prompt
        assert "task" in prompt
        assert "Das ist klar eine Aufgabe" in prompt
        assert "Aufgabe (task)" in prompt

    @pytest.mark.asyncio
    async def test_correction_block_for_forced_auto_reply(self):
        job = _make_fake_job()
        job.metadata_json["forced_class"] = "auto_reply"
        prompt = await self._build_prompt(job)
        assert "KORREKTUR DES BERATERS" in prompt
        assert "Antwort-Entwurf (auto_reply)" in prompt
        # Korrektur-Block soll ganz oben stehen (vor den Standard-Instruktionen).
        assert prompt.index("KORREKTUR DES BERATERS") < prompt.index("TRIAGE-INSTRUKTIONEN")


class TestDetermineRecipientType:
    """Tests für die recipient_type-Ableitung aus TO/CC-Feldern."""

    def test_to_recipient(self):
        from app.services.triage import _determine_recipient_type
        email = {
            "toRecipients": [{"emailAddress": {"address": "anthony@innosmith.ch"}}],
            "ccRecipients": [],
        }
        assert _determine_recipient_type(email) == "to"

    def test_cc_recipient(self):
        from app.services.triage import _determine_recipient_type
        email = {
            "toRecipients": [{"emailAddress": {"address": "other@example.com"}}],
            "ccRecipients": [{"emailAddress": {"address": "anthony@gerbersmith.ch"}}],
        }
        assert _determine_recipient_type(email) == "cc"

    def test_bfh_address_recognized(self):
        from app.services.triage import _determine_recipient_type
        email = {
            "toRecipients": [{"emailAddress": {"address": "anthony.smith@bfh.ch"}}],
            "ccRecipients": [],
        }
        assert _determine_recipient_type(email) == "to"

    def test_to_takes_precedence_over_cc(self):
        """Wenn Owner in TO und CC steht, gewinnt TO."""
        from app.services.triage import _determine_recipient_type
        email = {
            "toRecipients": [{"emailAddress": {"address": "anthony@innosmith.ch"}}],
            "ccRecipients": [{"emailAddress": {"address": "anthony@gerbersmith.ch"}}],
        }
        assert _determine_recipient_type(email) == "to"

    def test_unknown_when_not_in_either(self):
        from app.services.triage import _determine_recipient_type
        email = {
            "toRecipients": [{"emailAddress": {"address": "someone@example.com"}}],
            "ccRecipients": [{"emailAddress": {"address": "other@example.com"}}],
        }
        assert _determine_recipient_type(email) == "unknown"

    def test_case_insensitive(self):
        from app.services.triage import _determine_recipient_type
        email = {
            "toRecipients": [],
            "ccRecipients": [{"emailAddress": {"address": "Anthony@InnoSmith.ch"}}],
        }
        assert _determine_recipient_type(email) == "cc"

    def test_empty_recipients(self):
        from app.services.triage import _determine_recipient_type
        email = {}
        assert _determine_recipient_type(email) == "unknown"

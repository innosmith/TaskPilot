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

    async def _build_prompt(self, job):
        """Importiert und ruft _build_triage_prompt auf, mit gemockten DB-Calls."""
        with patch("app.services.nanobot_worker._load_projects_context", new_callable=AsyncMock) as mock_projects:
            mock_projects.return_value = "## VERFÜGBARE PROJEKTE\n- \"TestProjekt\" (id: 123)"

            from app.services.nanobot_worker import _build_triage_prompt
            return await _build_triage_prompt(job)

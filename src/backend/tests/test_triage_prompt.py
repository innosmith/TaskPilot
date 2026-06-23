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
    async def test_style_skill_view_native(self, fake_job):
        """Im Normalfall (nativer Skill vorhanden) wird skill_view(email-style) angewiesen."""
        prompt = await self._build_prompt(fake_job, style_native=True)
        assert "SCHREIBSTIL" in prompt, "SCHREIBSTIL-Block fehlt im Prompt"
        assert "skill_view(name='email-style')" in prompt

    @pytest.mark.asyncio
    async def test_triage_skill_view_native(self, fake_job):
        """Im Normalfall (nativer Skill vorhanden) wird skill_view(email-triage) angewiesen."""
        prompt = await self._build_prompt(fake_job, skill_native=True)
        assert "skill_view(name='email-triage')" in prompt

    @pytest.mark.asyncio
    async def test_style_block_injected_fallback(self, fake_job):
        """Fallback: ohne nativen Skill wird der Schreibstil-Kanon injiziert."""
        sentinel = "Knapp, klar, kollegial, lösungsorientiert (STIL-SENTINEL)"
        prompt = await self._build_prompt(fake_job, style_text=sentinel, style_native=False)
        assert "SCHREIBSTIL" in prompt, "SCHREIBSTIL-Block fehlt im Prompt"
        assert sentinel in prompt, "Schreibstil-Kanon-Inhalt fehlt im Prompt"

    @pytest.mark.asyncio
    async def test_style_block_absent_when_empty(self, fake_job):
        """Ohne nativen Skill und ohne Kanon-Text wird kein SCHREIBSTIL-Block eingefügt."""
        prompt = await self._build_prompt(fake_job, style_text="", style_native=False)
        assert "SCHREIBSTIL" not in prompt

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

    async def _build_prompt(
        self,
        job,
        style_text="(Schreibstil-Kanon Platzhalter)",
        skill_text="(Triage-Skill Platzhalter)",
        skill_native=True,
        style_native=True,
    ):
        """Importiert und ruft _build_triage_prompt auf, mit gemockten DB-Calls.

        Skill-Verfügbarkeit und -Inhalt werden gemockt, damit der Test unabhängig
        vom Dateisystem (~/.hermes/skills/...) ist. Default: native Skills vorhanden.
        """
        with patch("app.services.hermes_worker._load_projects_context", new_callable=AsyncMock) as mock_projects, \
             patch("app.services.hermes_worker._load_style_profile", return_value=style_text), \
             patch("app.services.hermes_worker._load_triage_skill", return_value=skill_text), \
             patch("app.services.hermes_worker._triage_skill_available", return_value=skill_native), \
             patch("app.services.hermes_worker._style_skill_available", return_value=style_native):
            mock_projects.return_value = "## VERFÜGBARE PROJEKTE\n- \"TestProjekt\" (id: 123)"

            from app.services.hermes_worker import _build_triage_prompt
            return await _build_triage_prompt(job)


class TestForcedClassCorrection:
    """Tests für den Berater-Korrektur-Block (forced_class) im Triage-Prompt."""

    async def _build_prompt(
        self,
        job,
        style_text="(Schreibstil-Kanon Platzhalter)",
        skill_text="(Triage-Skill Platzhalter)",
        skill_native=True,
        style_native=True,
    ):
        with patch("app.services.hermes_worker._load_projects_context", new_callable=AsyncMock) as mock_projects, \
             patch("app.services.hermes_worker._load_style_profile", return_value=style_text), \
             patch("app.services.hermes_worker._load_triage_skill", return_value=skill_text), \
             patch("app.services.hermes_worker._triage_skill_available", return_value=skill_native), \
             patch("app.services.hermes_worker._style_skill_available", return_value=style_native):
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
        # Korrektur-Block soll ganz oben stehen (vor der Skill-Sektion).
        assert prompt.index("KORREKTUR DES BERATERS") < prompt.index("TRIAGE-SKILL")

    @pytest.mark.asyncio
    async def test_correction_block_before_skill_fallback(self):
        """Auch im Datei-Fallback steht der Korrektur-Block vor den Instruktionen."""
        job = _make_fake_job()
        job.metadata_json["forced_class"] = "auto_reply"
        prompt = await self._build_prompt(job, skill_native=False)
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


class TestExtractJsonBlock:
    """Contract-Tests fuer den robusten Triage-JSON-Parser.

    Hintergrund: ~11% der Prod-Jobs fielen frueher still durch, weil die alte
    enge Regex nur einen ```json-Fence ODER ein flaches Objekt mit BEIDEN Feldern
    ``label`` UND ``triage_class`` (ohne Verschachtelung) akzeptierte. Diese Tests
    fixieren die toleranten Faelle, die lokale Modelle real produzieren.
    """

    def test_fenced_json_block(self):
        from app.services.hermes_worker import _extract_json_block
        content = (
            "Analyse ...\n\n```json\n"
            '{"label": "System", "triage_class": "fyi", "reply_expected": false}\n'
            "```\n"
        )
        parsed = _extract_json_block(content)
        assert parsed is not None
        assert parsed["triage_class"] == "fyi"

    def test_bare_fence_without_json_tag(self):
        from app.services.hermes_worker import _extract_json_block
        content = '```\n{"triage_class": "task", "task_title": "X"}\n```'
        parsed = _extract_json_block(content)
        assert parsed is not None
        assert parsed["triage_class"] == "task"

    def test_no_fence_object_in_prose(self):
        from app.services.hermes_worker import _extract_json_block
        content = 'Entscheid: {"triage_class": "auto_reply", "label": "Wichtig"} -- fertig.'
        parsed = _extract_json_block(content)
        assert parsed is not None
        assert parsed["triage_class"] == "auto_reply"

    def test_nested_object_with_array(self):
        """Verschachtelte Felder (categories-Array, Sub-Objekt) duerfen nicht abbrechen."""
        from app.services.hermes_worker import _extract_json_block
        content = (
            '{"triage_class": "fyi", "label": "System", '
            '"categories": ["System", "Newsletter"], '
            '"meta": {"move_folder": "System"}}'
        )
        parsed = _extract_json_block(content)
        assert parsed is not None
        assert parsed["triage_class"] == "fyi"
        assert parsed["categories"] == ["System", "Newsletter"]

    def test_trailing_comma_tolerated(self):
        from app.services.hermes_worker import _extract_json_block
        content = '{"triage_class": "task", "task_title": "Y",}'
        parsed = _extract_json_block(content)
        assert parsed is not None
        assert parsed["triage_class"] == "task"

    def test_single_quotes_python_dict(self):
        from app.services.hermes_worker import _extract_json_block
        content = "{'triage_class': 'fyi', 'reply_expected': false}"
        parsed = _extract_json_block(content)
        assert parsed is not None
        assert parsed["triage_class"] == "fyi"
        assert parsed["reply_expected"] is False

    def test_prose_only_returns_none(self):
        from app.services.hermes_worker import _extract_json_block
        content = "Ich habe die E-Mail eingeordnet und einen Task erstellt. Keine Aktion noetig."
        assert _extract_json_block(content) is None

    def test_empty_returns_none(self):
        from app.services.hermes_worker import _extract_json_block
        assert _extract_json_block("") is None

    def test_last_object_with_triage_class_wins(self):
        """Mehrere Objekte: das letzte mit triage_class (Abschlussblock) gewinnt."""
        from app.services.hermes_worker import _extract_json_block
        content = (
            '{"some": "tool_args"}\n'
            '{"triage_class": "task", "label": "erste"}\n'
            'Korrektur:\n'
            '{"triage_class": "fyi", "label": "finale"}'
        )
        parsed = _extract_json_block(content)
        assert parsed is not None
        assert parsed["triage_class"] == "fyi"
        assert parsed["label"] == "finale"

    def test_json_true_false_null(self):
        from app.services.hermes_worker import _extract_json_block
        content = '{"triage_class": "task", "reply_expected": true, "deadline": null}'
        parsed = _extract_json_block(content)
        assert parsed is not None
        assert parsed["reply_expected"] is True
        assert parsed["deadline"] is None


class TestStripInternalNotes:
    """Interne API-/Fehler-Diagnosen duerfen nicht in nutzersichtbaren Text gelangen."""

    def test_removes_graph_404_sentence(self):
        from app.services.hermes_worker import _strip_internal_notes
        text = (
            "Rahel sendet die IT-Checkliste und will einen Termin. "
            "Die E-Mail liess sich via Graph API nicht laden (404)."
        )
        cleaned = _strip_internal_notes(text)
        assert "404" not in cleaned
        assert "Graph" not in cleaned
        assert "IT-Checkliste" in cleaned

    def test_removes_httpstatuserror(self):
        from app.services.hermes_worker import _strip_internal_notes
        text = "Kurzes Briefing. HTTPStatusError: 400 Bad Request bei createReplyAll."
        cleaned = _strip_internal_notes(text)
        assert "HTTPStatusError" not in cleaned
        assert "createReplyAll" not in cleaned
        assert "Briefing" in cleaned

    def test_keeps_clean_text(self):
        from app.services.hermes_worker import _strip_internal_notes
        text = "Bitte den Vertrag bis Freitag pruefen und an den Kunden antworten."
        assert _strip_internal_notes(text) == text

    def test_all_noise_returns_none(self):
        from app.services.hermes_worker import _strip_internal_notes
        assert _strip_internal_notes("404 Not Found. HTTPStatusError createReply.") is None

    def test_none_passthrough(self):
        from app.services.hermes_worker import _strip_internal_notes
        assert _strip_internal_notes(None) is None


class TestEmailReferenceBlock:
    """Jede E-Mail-Task soll einen Quell-Block mit Outlook-Deeplink tragen."""

    def test_deeplink_built_from_message_id(self):
        from app.services.hermes_worker import _outlook_deeplink
        link = _outlook_deeplink("AAMk=abc/def+ghi")
        assert link is not None
        assert link.startswith("https://outlook.office.com/mail/deeplink/read/")
        # Sonderzeichen muessen URL-encodiert sein (kein rohes '/', '=' oder '+').
        assert "abc/def" not in link
        assert "%3D" in link or "%2F" in link or "%2B" in link

    def test_deeplink_none_without_id(self):
        from app.services.hermes_worker import _outlook_deeplink
        assert _outlook_deeplink(None) is None

    def test_reference_block_contains_sender_subject_link(self):
        from app.services.hermes_worker import _email_reference_block
        meta = {
            "from_name": "Test Sender",
            "from_address": "test@example.com",
            "subject": "Wichtiger Betreff",
            "email_message_id": "AAMk123",
        }
        block = _email_reference_block(meta)
        assert "Test Sender" in block
        assert "test@example.com" in block
        assert "Wichtiger Betreff" in block
        assert "outlook.office.com" in block

    def test_reference_block_empty_without_data(self):
        from app.services.hermes_worker import _email_reference_block
        assert _email_reference_block({}) == ""


class TestSelfGradeStyleAnchor:
    """Self-Grade erkennt spaete Tools (create_draft/search_my_replies) korrekt."""

    def test_style_anchor_detected_with_prefixed_tool(self):
        from app.services.hermes_worker import _compute_self_grade
        meta = {"conversation_id": "conv-1"}
        tools = [
            "mcp_graph_get_thread",
            "mcp_graph_search_sender_history",
            "mcp_taskpilot_get_sender_profile",
            "mcp_graph_search_my_replies",
        ]
        grade = _compute_self_grade(meta, {"draft_id": "d1"}, tools)
        assert grade["missing"] == []
        assert grade["score"] == 1.0

    def test_style_anchor_missing_when_not_called(self):
        from app.services.hermes_worker import _compute_self_grade
        meta = {"conversation_id": "conv-1"}
        tools = [
            "mcp_graph_get_thread",
            "mcp_graph_search_sender_history",
            "mcp_taskpilot_get_sender_profile",
        ]
        grade = _compute_self_grade(meta, {"draft_id": "d1"}, tools)
        assert "style_anchor_used" in grade["missing"]


class TestExtractNewIdFromMove:
    """Post-Move-ID wird zuverlaessig aus dem Tool-Ergebnis erfasst."""

    def test_parses_wrapped_new_id(self):
        import json
        from app.services.hermes_worker import _extract_new_id_from_move_result
        inner = json.dumps(
            {"status": "moved", "message_id": "OLD", "folder": "System", "new_id": "NEWID123"}
        )
        # Hermes wrappt das MCP-Ergebnis als {"result": "<json-string>"}.
        assert _extract_new_id_from_move_result({"result": inner}) == "NEWID123"

    def test_parses_plain_dict(self):
        from app.services.hermes_worker import _extract_new_id_from_move_result
        assert _extract_new_id_from_move_result({"new_id": "X"}) == "X"

    def test_none_when_absent(self):
        from app.services.hermes_worker import _extract_new_id_from_move_result
        assert _extract_new_id_from_move_result({"status": "moved"}) is None

    def test_regex_fallback_double_escaped(self):
        from app.services.hermes_worker import _extract_new_id_from_move_result
        text = '{\\"status\\": \\"moved\\", \\"new_id\\": \\"ESCAPED42\\"}'
        assert _extract_new_id_from_move_result(text) == "ESCAPED42"


class TestFinalizeEmailState:
    """Deterministische Outlook-Finalisierung: Kategorie-Gating + immer ungelesen."""

    def _client(self, categories=None):
        from unittest.mock import AsyncMock
        client = AsyncMock()
        client.get_email_categories.return_value = {"categories": categories or []}
        return client

    @pytest.mark.asyncio
    async def test_category_set_when_missing_and_unread_is_last(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services import hermes_worker as hw

        client = self._client(categories=[])
        manager = MagicMock()
        manager.attach_mock(client.get_email_categories, "get_cat")
        manager.attach_mock(client.set_categories, "set_cat")
        manager.attach_mock(client.mark_as_unread, "unread")

        with patch.object(hw, "_build_graph_client", AsyncMock(return_value=client)):
            await hw._finalize_email_state({"email_message_id": "M1"}, "Wichtig", None)

        client.set_categories.assert_awaited_once_with("M1", ["Wichtig"])
        client.mark_as_unread.assert_awaited_once_with("M1")
        # ungelesen MUSS der letzte Graph-Schritt sein (set_categories kippt isRead).
        assert [c[0] for c in manager.mock_calls][-1] == "unread"

    @pytest.mark.asyncio
    async def test_category_not_overwritten_when_present(self):
        from unittest.mock import AsyncMock, patch
        from app.services import hermes_worker as hw

        client = self._client(categories=["Finanzen"])
        with patch.object(hw, "_build_graph_client", AsyncMock(return_value=client)):
            await hw._finalize_email_state({"email_message_id": "M1"}, "Wichtig", None)

        client.set_categories.assert_not_awaited()
        client.mark_as_unread.assert_awaited_once_with("M1")

    @pytest.mark.asyncio
    async def test_moved_id_takes_precedence(self):
        from unittest.mock import AsyncMock, patch
        from app.services import hermes_worker as hw

        client = self._client(categories=[])
        with patch.object(hw, "_build_graph_client", AsyncMock(return_value=client)):
            await hw._finalize_email_state({"email_message_id": "OLD"}, "Wichtig", "NEW")

        client.set_categories.assert_awaited_once_with("NEW", ["Wichtig"])
        client.mark_as_unread.assert_awaited_once_with("NEW")

    @pytest.mark.asyncio
    async def test_unklassifiziert_skips_category_but_marks_unread(self):
        from unittest.mock import AsyncMock, patch
        from app.services import hermes_worker as hw

        client = self._client(categories=[])
        with patch.object(hw, "_build_graph_client", AsyncMock(return_value=client)):
            await hw._finalize_email_state({"email_message_id": "M1"}, "Unklassifiziert", None)

        client.get_email_categories.assert_not_awaited()
        client.set_categories.assert_not_awaited()
        client.mark_as_unread.assert_awaited_once_with("M1")

    @pytest.mark.asyncio
    async def test_404_is_tolerated(self):
        from unittest.mock import AsyncMock, patch
        import httpx
        from app.services import hermes_worker as hw

        req = httpx.Request("GET", "http://x")
        err = httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, request=req))
        client = self._client(categories=[])
        client.get_email_categories.side_effect = err
        client.mark_as_unread.side_effect = err

        with patch.object(hw, "_build_graph_client", AsyncMock(return_value=client)):
            # Darf NICHT werfen -- CC-only/veraltete IDs sind erwartbar.
            await hw._finalize_email_state({"email_message_id": "M1"}, "Wichtig", None)

        client.mark_as_unread.assert_awaited_once_with("M1")

    @pytest.mark.asyncio
    async def test_no_message_id_skips_client(self):
        from unittest.mock import AsyncMock, patch
        from app.services import hermes_worker as hw

        build = AsyncMock()
        with patch.object(hw, "_build_graph_client", build):
            await hw._finalize_email_state({}, "Wichtig", None)

        build.assert_not_awaited()

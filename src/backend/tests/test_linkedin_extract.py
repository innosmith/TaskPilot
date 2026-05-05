"""Tests für den LLM-basierten LinkedIn-Profil-Extraktions-Endpoint.

Prüft:
- HTML-Cleaning (Script/Style-Entfernung)
- JSON-Extraktion aus verschiedenen LLM-Output-Formaten
- Erfolgreiche Extraktion mit gemocktem LiteLLM
- Fehlerbehandlung bei ungültigem LLM-Output
- Validierung der Request-Parameter
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routers.linkedin import _clean_input, _extract_json, ExtractProfileRequest

SAMPLE_LINKEDIN_HTML = """
<section data-member-id="123456">
  <h1>Max Mustermann</h1>
  <p>Senior Consultant bei InnoSmith GmbH</p>
  <p>Bern, Schweiz</p>
  <a href="/company/innosmith">
    <span>InnoSmith GmbH</span>
  </a>
  <img src="https://media.licdn.com/dms/image/profile-displayphoto-shrink_400_400/abc123" />
</section>
"""

SAMPLE_NOISY_HTML = """
<html>
<head>
  <script>var tracking = true; console.log('spy');</script>
  <style>.hidden { display: none; }</style>
</head>
<body>
  <section>
    <h1>Anna Beispiel</h1>
    <p>CTO at TechCorp</p>
  </section>
  <script>analytics.track('view');</script>
</body>
</html>
"""


class TestInputCleaning:

    def test_removes_script_tags(self):
        cleaned = _clean_input(SAMPLE_NOISY_HTML)
        assert "tracking" not in cleaned
        assert "analytics.track" not in cleaned

    def test_removes_style_tags(self):
        cleaned = _clean_input(SAMPLE_NOISY_HTML)
        assert ".hidden" not in cleaned
        assert "display: none" not in cleaned

    def test_preserves_content(self):
        cleaned = _clean_input(SAMPLE_NOISY_HTML)
        assert "Anna Beispiel" in cleaned
        assert "CTO at TechCorp" in cleaned

    def test_handles_empty_input(self):
        assert _clean_input("") == ""

    def test_handles_plain_text(self):
        result = _clean_input("Einfacher Text ohne HTML")
        assert "Einfacher Text" in result

    def test_handles_linkedin_plaintext(self):
        text = "Lars Kaiser\nUrbanist @ Urban Equipe\nBern, Schweiz\n\nBerufserfahrung\nUrbanist\nUrban Equipe\nOkt 2018 – Heute"
        result = _clean_input(text)
        assert "Lars Kaiser" in result
        assert "Urban Equipe" in result
        assert "Berufserfahrung" in result


class TestJsonExtraction:

    def test_plain_json(self):
        result = _extract_json('{"name": "Test"}')
        assert result["name"] == "Test"

    def test_json_in_code_block(self):
        text = '```json\n{"name": "Test"}\n```'
        result = _extract_json(text)
        assert result["name"] == "Test"

    def test_json_in_bare_code_block(self):
        text = '```\n{"name": "Test"}\n```'
        result = _extract_json(text)
        assert result["name"] == "Test"

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("Das ist kein JSON")

    def test_whitespace_around_json(self):
        result = _extract_json('  \n {"name": "Test"} \n ')
        assert result["name"] == "Test"


class TestExtractProfileRequest:

    def test_rejects_short_html(self):
        with pytest.raises(Exception):
            ExtractProfileRequest(html="<p>kurz</p>")

    def test_accepts_valid_html(self):
        req = ExtractProfileRequest(html=SAMPLE_LINKEDIN_HTML)
        assert len(req.html) > 50


def _mock_litellm_response(content: dict) -> SimpleNamespace:
    """Erzeugt ein Mock-Response-Objekt wie von litellm.acompletion."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(content))
            )
        ]
    )


class TestExtractProfileEndpoint:

    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        from app.routers.linkedin import extract_profile_from_html, ExtractProfileRequest

        mock_user = SimpleNamespace(
            id=1, email="test@example.com", role="owner", settings={}
        )

        expected_output = {
            "name": "Max Mustermann",
            "headline": "Senior Consultant bei InnoSmith GmbH",
            "location": "Bern, Schweiz",
            "job_title": "Senior Consultant",
            "companies": ["InnoSmith GmbH"],
        }

        with patch("app.routers.linkedin.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_mock_litellm_response(expected_output)
            )

            body = ExtractProfileRequest(html=SAMPLE_LINKEDIN_HTML)
            result = await extract_profile_from_html(body=body, user=mock_user)

            assert result.name == "Max Mustermann"
            assert result.headline == "Senior Consultant bei InnoSmith GmbH"
            assert result.location == "Bern, Schweiz"
            assert result.job_title == "Senior Consultant"
            assert "InnoSmith GmbH" in result.companies
            assert result.extraction_method == "llm"

    @pytest.mark.asyncio
    async def test_empty_fields_from_llm(self):
        from app.routers.linkedin import extract_profile_from_html, ExtractProfileRequest

        mock_user = SimpleNamespace(
            id=1, email="test@example.com", role="owner", settings={}
        )

        empty_output = {
            "name": "",
            "headline": "",
            "location": "",
            "job_title": "",
            "companies": [],
        }

        with patch("app.routers.linkedin.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_mock_litellm_response(empty_output)
            )

            body = ExtractProfileRequest(html=SAMPLE_LINKEDIN_HTML)
            result = await extract_profile_from_html(body=body, user=mock_user)

            assert result.name == ""
            assert result.companies == []

    @pytest.mark.asyncio
    async def test_invalid_json_from_llm(self):
        from app.routers.linkedin import extract_profile_from_html, ExtractProfileRequest
        from fastapi import HTTPException

        mock_user = SimpleNamespace(
            id=1, email="test@example.com", role="owner", settings={}
        )

        broken_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Das ist kein JSON")
                )
            ]
        )

        with patch("app.routers.linkedin.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=broken_response)

            body = ExtractProfileRequest(html=SAMPLE_LINKEDIN_HTML)
            with pytest.raises(HTTPException) as exc_info:
                await extract_profile_from_html(body=body, user=mock_user)
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_llm_connection_error(self):
        from app.routers.linkedin import extract_profile_from_html, ExtractProfileRequest
        from fastapi import HTTPException

        mock_user = SimpleNamespace(
            id=1, email="test@example.com", role="owner", settings={}
        )

        with patch("app.routers.linkedin.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=ConnectionError("API nicht erreichbar")
            )

            body = ExtractProfileRequest(html=SAMPLE_LINKEDIN_HTML)
            with pytest.raises(HTTPException) as exc_info:
                await extract_profile_from_html(body=body, user=mock_user)
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_llm_empty_content(self):
        from app.routers.linkedin import extract_profile_from_html, ExtractProfileRequest
        from fastapi import HTTPException

        mock_user = SimpleNamespace(
            id=1, email="test@example.com", role="owner", settings={}
        )

        empty_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="")
                )
            ]
        )

        with patch("app.routers.linkedin.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=empty_response)

            body = ExtractProfileRequest(html=SAMPLE_LINKEDIN_HTML)
            with pytest.raises(HTTPException) as exc_info:
                await extract_profile_from_html(body=body, user=mock_user)
            assert exc_info.value.status_code == 502

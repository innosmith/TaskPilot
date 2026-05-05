"""Router für LLM-basierte LinkedIn-Profil-Extraktion.

Nimmt rohes HTML einer LinkedIn-Profilseite entgegen und extrahiert
strukturierte Profildaten via LLM. Dient als Fallback, wenn die
heuristischen Selektoren im Chrome-Extension Content-Script versagen
(z.B. nach LinkedIn-DOM-Änderungen).

LinkedIn-Profildaten sind öffentlich → Cloud-LLMs (Gemini Flash,
GPT-4o-mini) sind erlaubt und massiv schneller als lokale Modelle.
"""

import json
import logging
import os
import re

import litellm
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user
from app.config import get_settings
from app.models import User

logger = logging.getLogger("taskpilot.linkedin")
litellm.drop_params = True

router = APIRouter(prefix="/api/linkedin", tags=["linkedin"])

LINKEDIN_EXTRACT_MODEL = "openai/gpt-4.1-nano"

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "linkedin_profile",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Vollständiger Name (Vorname + Nachname)"},
                "headline": {"type": "string", "description": "Berufsbezeichnung / Headline"},
                "location": {"type": "string", "description": "Standort / Ort"},
                "job_title": {"type": "string", "description": "Aktuelle Berufsbezeichnung (ohne Firma)"},
                "companies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste der aktuellen Firmen / Organisationen",
                },
            },
            "required": ["name", "headline", "location", "job_title", "companies"],
            "additionalProperties": False,
        },
    },
}

SYSTEM_PROMPT = (
    "Du extrahierst strukturierte Profildaten aus LinkedIn-Profiltext. "
    "Der Input kann HTML oder Plaintext sein. "
    "Antworte NUR mit validem JSON, kein anderer Text. Felder: "
    "name (Vorname + Nachname), headline (Berufsbezeichnung/Tagline), "
    "location (Standort/Ort, z.B. 'Bern, Schweiz'), "
    "job_title (aktuelle Berufsbezeichnung aus dem Experience/Berufserfahrung-Bereich, NICHT die Headline), "
    "companies (Liste der aktuellen Firmen/Organisationen aus dem Experience-Bereich). "
    "WICHTIG: job_title soll die konkrete Rolle aus der Berufserfahrung sein "
    "(z.B. 'Leiterin Internal Services'), nicht die Headline. "
    "Falls ein Feld nicht vorhanden ist, gib einen leeren String "
    "bzw. ein leeres Array zurück. Erfinde keine Daten."
)


def _setup_api_keys():
    """API-Keys aus Settings als Env-Vars setzen (wie chat.py)."""
    s = get_settings()
    if s.openai_api_key:
        os.environ["OPENAI_API_KEY"] = s.openai_api_key
    if s.gemini_api_key:
        os.environ["GEMINI_API_KEY"] = s.gemini_api_key


def _clean_input(text: str) -> str:
    """Bereinigt Input — funktioniert sowohl mit HTML als auch Plaintext."""
    if "<" in text and ">" in text:
        try:
            import lxml.html as LH
            from lxml.html.clean import Cleaner

            cleaner = Cleaner(
                scripts=True, javascript=True, style=True,
                inline_style=True, safe_attrs_only=False,
            )
            doc = LH.fromstring(text)
            cleaned = cleaner.clean_html(doc)
            return LH.tostring(cleaned, encoding="unicode")
        except Exception:
            cleaned = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            cleaned = re.sub(r"<style[^>]*>.*?</style>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
            cleaned = re.sub(r"<[^>]+>", " ", cleaned)
            return re.sub(r"\s+", " ", cleaned).strip()
    return re.sub(r"\s{3,}", "\n", text).strip()


def _extract_json(text: str) -> dict:
    """Extrahiert JSON aus LLM-Output (auch aus Markdown-Code-Blöcken)."""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    raise json.JSONDecodeError("Kein JSON gefunden", text, 0)


class ExtractProfileRequest(BaseModel):
    html: str = Field(..., min_length=50, max_length=500_000, description="LinkedIn-Profilinhalt (HTML oder Plaintext)")


class ExtractedProfile(BaseModel):
    name: str = ""
    headline: str = ""
    location: str = ""
    job_title: str = ""
    companies: list[str] = []
    extraction_method: str = "llm"


@router.post("/extract-profile", response_model=ExtractedProfile)
async def extract_profile_from_html(
    body: ExtractProfileRequest,
    user: User = Depends(get_current_user),
):
    """Extrahiert LinkedIn-Profildaten aus rohem HTML via Cloud-LLM."""
    _setup_api_keys()

    clean_html = _clean_input(body.html)
    if len(clean_html) > 100_000:
        clean_html = clean_html[:100_000]

    try:
        response = await litellm.acompletion(
            model=LINKEDIN_EXTRACT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": clean_html},
            ],
            response_format=RESPONSE_FORMAT,
            temperature=0,
            timeout=30,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM hat keinen Inhalt zurückgegeben")

        data = _extract_json(content)

        return ExtractedProfile(
            name=data.get("name", ""),
            headline=data.get("headline", ""),
            location=data.get("location", ""),
            job_title=data.get("job_title", ""),
            companies=data.get("companies", []),
            extraction_method="llm",
        )

    except json.JSONDecodeError as exc:
        logger.warning("LLM-Antwort war kein valides JSON: %s", exc)
        raise HTTPException(status_code=502, detail="LLM-Antwort konnte nicht als JSON geparst werden")
    except Exception as exc:
        logger.error("LinkedIn-Profil-Extraktion fehlgeschlagen: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"LLM-Extraktion fehlgeschlagen: {exc}")

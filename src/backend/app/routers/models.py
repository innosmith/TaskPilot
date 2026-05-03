"""Router für verfügbare LLM-Modelle — dynamisch von Ollama + Cloud-APIs."""

import logging
import time

import httpx
import litellm
from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.config import get_settings
from app.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/models", tags=["models"])

_cache: dict = {"data": None, "expires_at": 0.0}
CACHE_TTL_SECONDS = 300

OLLAMA_BASE = "http://localhost:11434"

KNOWN_ANTHROPIC_MODELS = [
    ("claude-opus-4-7", "Claude Opus 4.7"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
    ("claude-haiku-4-5", "Claude Haiku 4.5"),
    ("claude-opus-4-6", "Claude Opus 4.6"),
    ("claude-sonnet-4-5", "Claude Sonnet 4.5"),
]

KNOWN_PERPLEXITY_MODELS = [
    ("sonar-pro", "Sonar Pro (Web Search)"),
    ("sonar", "Sonar (Web Search)"),
    ("sonar-deep-research", "Sonar Deep Research"),
    ("sonar-reasoning-pro", "Sonar Reasoning Pro"),
    ("sonar-reasoning", "Sonar Reasoning"),
]


def _get_capabilities(model_id: str) -> list[str]:
    """Welche Modi ein Modell unterstützt — dynamisch via litellm."""
    caps = ["chat"]
    provider = model_id.split("/")[0] if "/" in model_id else ""
    model = model_id.split("/")[-1] if "/" in model_id else model_id

    if provider == "gemini":
        caps.append("web_search")
        if "deep-research" in model or "thinking" in model:
            caps.append("deep_research")
    if provider == "perplexity":
        caps.append("web_search")
        if "deep-research" in model:
            caps.append("deep_research")

    try:
        if litellm.supports_reasoning(model=model_id):
            caps.append("thinking")
    except Exception:
        pass

    return caps


def _make_entry(model_id: str, friendly_name: str, model_type: str, provider: str) -> dict:
    return {
        "id": model_id,
        "name": friendly_name,
        "type": model_type,
        "provider": provider,
        "capabilities": _get_capabilities(model_id),
    }


async def _fetch_ollama_models() -> list[dict]:
    """Alle lokal verfuegbaren Ollama-Modelle abfragen."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("models", []):
                    name = m["name"]
                    model_id = f"ollama/{name}"
                    size_gb = m.get("size", 0) / (1024 ** 3)
                    size_label = f" ({size_gb:.0f}GB)" if size_gb > 1 else ""
                    friendly = name.replace(":", " ").replace("-", " ").title() + size_label
                    models.append(_make_entry(model_id, friendly, "local", "ollama"))
                return models
    except Exception as e:
        logger.warning("Ollama nicht erreichbar: %s", e)
    return []


async def _fetch_openai_models() -> list[dict]:
    """OpenAI-Modelle via /v1/models abfragen (kostenloser API-Call)."""
    settings = get_settings()
    if not settings.openai_api_key:
        return []

    RELEVANT_PREFIXES = ("gpt-4", "gpt-3.5", "o1", "o3", "o4")
    EXCLUDE = ("instruct", "audio", "realtime", "search", "tts", "dall-e", "whisper", "embed", "moderation", "transcribe", "diarize")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("data", []):
                    mid = m["id"]
                    if not any(mid.startswith(p) for p in RELEVANT_PREFIXES):
                        continue
                    if any(x in mid for x in EXCLUDE):
                        continue
                    model_id = f"openai/{mid}"
                    models.append(_make_entry(model_id, mid, "cloud", "openai"))
                models.sort(key=lambda x: x["id"])
                return models
    except Exception as e:
        logger.warning("OpenAI Models API nicht erreichbar: %s", e)
    return []


async def _fetch_gemini_models() -> list[dict]:
    """Google Gemini-Modelle via API abfragen (kostenloser Call)."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": settings.gemini_api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if not name.startswith("models/gemini-"):
                        continue
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" not in methods:
                        continue
                    if any(x in name for x in ("tts", "robotics", "image", "customtools")):
                        continue
                    short = name.replace("models/", "")
                    model_id = f"gemini/{short}"
                    display = m.get("displayName", short)
                    models.append(_make_entry(model_id, display, "cloud", "gemini"))
                return models
    except Exception as e:
        logger.warning("Gemini Models API nicht erreichbar: %s", e)
    return []


def _get_anthropic_models() -> list[dict]:
    """Bekannte Anthropic-Modelle (kein kostenloser List-Endpoint)."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return []
    return [
        _make_entry(f"anthropic/{mid}", name, "cloud", "anthropic")
        for mid, name in KNOWN_ANTHROPIC_MODELS
    ]


def _get_perplexity_models() -> list[dict]:
    """Bekannte Perplexity-Modelle (kein kostenloser List-Endpoint)."""
    settings = get_settings()
    if not settings.perplexity_api_key:
        return []
    return [
        _make_entry(f"perplexity/{mid}", name, "cloud", "perplexity")
        for mid, name in KNOWN_PERPLEXITY_MODELS
    ]


async def _fetch_all_models() -> dict:
    """Alle verfuegbaren Modelle von allen Providern sammeln."""
    import asyncio

    ollama_task = asyncio.create_task(_fetch_ollama_models())
    openai_task = asyncio.create_task(_fetch_openai_models())
    gemini_task = asyncio.create_task(_fetch_gemini_models())

    ollama_models = await ollama_task
    openai_models = await openai_task
    gemini_models = await gemini_task
    anthropic_models = _get_anthropic_models()
    perplexity_models = _get_perplexity_models()

    local_models = ollama_models
    cloud_models = openai_models + anthropic_models + gemini_models + perplexity_models

    return {"local": local_models, "cloud": cloud_models}


@router.get("/available")
async def list_available_models(user: User = Depends(get_current_user)) -> dict:
    """Alle verfügbaren LLM-Modelle für die Einstellungsseite."""
    now = time.time()
    if _cache["data"] and now < _cache["expires_at"]:
        return _cache["data"]
    result = await _fetch_all_models()
    _cache["data"] = result
    _cache["expires_at"] = now + CACHE_TTL_SECONDS
    return result


@router.get("")
async def list_models(user: User = Depends(get_current_user)) -> dict:
    """Vom User aktivierte LLM-Modelle."""
    now = time.time()
    if not (_cache["data"] and now < _cache["expires_at"]):
        result = await _fetch_all_models()
        _cache["data"] = result
        _cache["expires_at"] = now + CACHE_TTL_SECONDS

    all_models = _cache["data"]
    settings = user.settings or {}
    llm_providers = settings.get("llm_providers", {})

    if not llm_providers:
        return all_models

    enabled_model_ids = set()
    for provider_config in llm_providers.values():
        if provider_config.get("enabled", False):
            enabled_model_ids.update(provider_config.get("models", []))

    if not enabled_model_ids:
        return all_models

    return {
        "local": [m for m in all_models.get("local", []) if m["id"] in enabled_model_ids],
        "cloud": [m for m in all_models.get("cloud", []) if m["id"] in enabled_model_ids],
    }


@router.post("/cache/clear")
async def clear_cache(user: User = Depends(get_current_user)) -> dict:
    """Modell-Cache leeren, damit beim naechsten Abruf neu geladen wird."""
    _cache["data"] = None
    _cache["expires_at"] = 0.0
    return {"ok": True}

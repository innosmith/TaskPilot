"""Router fuer verfuegbare LLM-Modelle (via LiteLLM Gateway)."""

import logging
import time

import httpx
from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.config import get_settings
from app.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/models", tags=["models"])

_cache: dict = {"data": None, "expires_at": 0.0}
CACHE_TTL_SECONDS = 300


async def _fetch_models_from_litellm() -> dict:
    """LiteLLM /model/info abfragen und nach Typ gruppieren."""
    settings = get_settings()
    base_url = settings.litellm_base_url.rstrip("/")

    local_models = []
    cloud_models = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/model/info")
            if resp.status_code == 200:
                data = resp.json()
                for model_info in data.get("data", []):
                    model_name = model_info.get("model_name", "")
                    entry = {
                        "id": model_name,
                        "name": _friendly_name(model_name),
                        "type": "local" if model_name.startswith("ollama/") else "cloud",
                        "provider": model_name.split("/")[0] if "/" in model_name else "unknown",
                    }
                    if entry["type"] == "local":
                        local_models.append(entry)
                    else:
                        cloud_models.append(entry)
    except Exception as e:
        logger.warning("LiteLLM nicht erreichbar (%s), verwende Fallback-Modelle", e)

    if not local_models and not cloud_models:
        local_models = [
            {"id": "ollama/qwen3.5:35b", "name": "Qwen 3.5 35B", "type": "local", "provider": "ollama"},
            {"id": "ollama/qwen3.5:9b", "name": "Qwen 3.5 9B (schnell)", "type": "local", "provider": "ollama"},
            {"id": "ollama/qwen3:32b", "name": "Qwen 3 32B", "type": "local", "provider": "ollama"},
            {"id": "ollama/gemma4:31b", "name": "Gemma 4 31B", "type": "local", "provider": "ollama"},
        ]
        cloud_models = [
            {"id": "anthropic/claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "type": "cloud", "provider": "anthropic"},
            {"id": "openai/gpt-4o", "name": "GPT-4o", "type": "cloud", "provider": "openai"},
            {"id": "gemini/gemini-2.5-pro", "name": "Gemini 2.5 Pro", "type": "cloud", "provider": "gemini"},
        ]

    return {"local": local_models, "cloud": cloud_models}


def _friendly_name(model_id: str) -> str:
    """Maschinenlesbare Modell-ID in lesbaren Namen umwandeln."""
    name_map = {
        "ollama/qwen3.5:35b": "Qwen 3.5 35B",
        "ollama/qwen3.5:9b": "Qwen 3.5 9B (schnell)",
        "ollama/qwen3:32b": "Qwen 3 32B",
        "ollama/gemma4:31b": "Gemma 4 31B",
        "anthropic/claude-sonnet-4-20250514": "Claude Sonnet 4",
        "anthropic/claude-3-5-haiku-20241022": "Claude 3.5 Haiku",
        "openai/gpt-4o": "GPT-4o",
        "openai/gpt-4o-mini": "GPT-4o Mini",
        "gemini/gemini-2.5-pro": "Gemini 2.5 Pro",
        "gemini/gemini-2.5-flash": "Gemini 2.5 Flash",
    }
    return name_map.get(model_id, model_id.split("/")[-1] if "/" in model_id else model_id)


@router.get("")
async def list_models(user: User = Depends(get_current_user)) -> dict:
    """Verfuegbare LLM-Modelle (gecached, 5 Min TTL)."""
    now = time.time()
    if _cache["data"] and now < _cache["expires_at"]:
        return _cache["data"]

    result = await _fetch_models_from_litellm()
    _cache["data"] = result
    _cache["expires_at"] = now + CACHE_TTL_SECONDS
    return result

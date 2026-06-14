"""Lokale Embeddings fuer das episodische Agent-Gedaechtnis.

Nutzt bewusst das lokale Ollama-Modell (Default ``Qwen3-Embedding-0.6B``, 1024-dim) statt eines
Cloud-Providers, damit auch vertrauliche Inhalte indexiert werden duerfen, ohne
die Datenklasse zu verletzen. Alle Funktionen sind **best-effort**: faellt Ollama
aus oder ist das Modell nicht vorhanden, geben sie ``None`` zurueck und der
aufrufende Pfad (Job-Verarbeitung) laeuft ungestoert weiter.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("taskpilot.embeddings")

# Qwen3-Embedding ist instruction-aware: ein Instruct-Prefix auf der QUERY-Seite
# (nicht auf der Dokument-Seite) verbessert Retrieval um 1-5 %. Instruktionen
# werden laut Qwen-Empfehlung auf Englisch formuliert, auch bei deutschen Inhalten.
QUERY_INSTRUCT = (
    "Instruct: Given a new email triage situation, retrieve similar past cases "
    "and how they were ultimately handled.\nQuery: "
)


async def embed_text(text: str, *, is_query: bool = False) -> list[float] | None:
    """Erzeugt ein Embedding fuer ``text`` via lokalem Ollama.

    ``is_query=True`` stellt der Eingabe den instruction-aware Query-Prefix voran
    (nur fuer Recall-Anfragen; Dokumente/Episoden werden ohne Prefix eingebettet).

    Gibt ``None`` zurueck, wenn Ollama nicht erreichbar ist, das Modell fehlt
    oder die Antwort unerwartet ist. Niemals Exceptions nach aussen werfen.
    """
    cfg = get_settings()
    clean = (text or "").strip()
    if not clean:
        return None

    prompt = (QUERY_INSTRUCT + clean) if is_query else clean
    base = cfg.ollama_base_url.rstrip("/")
    payload = {"model": cfg.embed_model, "prompt": prompt[:8000]}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{base}/api/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - best-effort, darf Job nicht stoppen
        logger.warning("Embedding fehlgeschlagen (Modell=%s): %s", cfg.embed_model, exc)
        return None

    vec = data.get("embedding")
    if not isinstance(vec, list) or not vec:
        logger.warning("Embedding-Antwort ohne 'embedding'-Feld")
        return None

    if len(vec) != cfg.embed_dim:
        logger.warning(
            "Embedding-Dimension %d != erwartete %d (Modell=%s) -- verworfen",
            len(vec), cfg.embed_dim, cfg.embed_model,
        )
        return None
    return [float(x) for x in vec]


def to_pgvector(vec: list[float]) -> str:
    """Formatiert einen Float-Vektor als pgvector-Literal ('[0.1,0.2,...]')."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

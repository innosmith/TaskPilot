"""Embedding-Erzeugung für SIGNA-Signale.

Nutzt OpenAI `text-embedding-3-large` mit `dimensions=1536`, damit die Vektoren
exakt in die vorhandene Spalte `isi_signals.embedding vector(1536)` passen.

Bewusst ohne Abhängigkeit zu TaskPilot-internen Modulen gehalten, damit der
Baustein 1:1 in den geplanten SIGNA-Neubau übernommen werden kann. Der API-Key
wird aus der Umgebung gelesen (`TP_OPENAI_API_KEY` oder `OPENAI_API_KEY`).
"""

import os
import time

import litellm

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 1536

# OpenAI erlaubt grosse Batches; konservativ wählen, um Token-Limits einzuhalten.
DEFAULT_BATCH_SIZE = 128
MAX_RETRIES = 5


def _api_key() -> str:
    key = os.environ.get("TP_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "Kein OpenAI-API-Key gefunden (TP_OPENAI_API_KEY oder OPENAI_API_KEY)."
        )
    return key


def _embed_batch(texts: list[str], api_key: str) -> list[list[float]]:
    """Ein einzelner Embedding-Request mit einfachem Retry/Backoff."""
    delay = 2.0
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = litellm.embedding(
                model=EMBED_MODEL,
                input=texts,
                dimensions=EMBED_DIM,
                api_key=api_key,
            )
            # Reihenfolge anhand 'index' sicherstellen
            data = sorted(resp.data, key=lambda d: d["index"])
            return [d["embedding"] for d in data]
        except Exception as err:  # noqa: BLE001 - Backoff für transiente Fehler
            last_err = err
            if attempt == MAX_RETRIES:
                break
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
    raise RuntimeError(f"Embedding-Request nach {MAX_RETRIES} Versuchen fehlgeschlagen: {last_err}")


def embed_texts(texts: list[str], batch_size: int = DEFAULT_BATCH_SIZE) -> list[list[float]]:
    """Erzeugt Embeddings für eine Liste von Texten (in Batches)."""
    if not texts:
        return []
    api_key = _api_key()
    out: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        out.extend(_embed_batch(batch, api_key))
    return out


def embed_query(text: str) -> list[float]:
    """Erzeugt ein einzelnes Query-Embedding (gleiches Modell/Dimension)."""
    return embed_texts([text])[0]

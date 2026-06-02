"""Backfill der Embeddings für SIGNA-Signale.

Liest Signale ohne Embedding aus `isi_signals`, erzeugt Vektoren mit
`text-embedding-3-large` (1536 Dim) und schreibt sie in die Spalte `embedding`.

- Schreibverbindung über Rolle `signa_embedder` (TP_ISI_WRITE_USER/SECRET).
- Idempotent: standardmässig nur Zeilen mit `embedding IS NULL`.
- Zeitfenster via `--since` (z. B. 3m, 90d, 2026-01-01) oder `--all`.

Aufruf (aus dem Repo-Root, prod-Umgebung):
    python -m src.signa.embed_backfill --since 3m
    python src/signa/embed_backfill.py --since 3m --dry-run
"""

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# .env.prod laden (Write-User + OpenAI-Key liegen dort). Bestehende Env-Vars
# werden nicht überschrieben (override=False), damit explizite Vorgaben gewinnen.
_ENV_FILE = _PROJECT_ROOT / ".env.prod"
if _ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE, override=False)

# Import nach sys.path-Anpassung, damit das Skript auch direkt lauffähig ist.
sys.path.insert(0, str(_PROJECT_ROOT))
from src.signa.embeddings import EMBED_DIM, embed_texts  # noqa: E402
from src.signa.signa_client import SignaConfig  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("signa.backfill")

MAX_TEXT_CHARS = 8000


def parse_since(value: str | None) -> datetime | None:
    """Wandelt '3m' / '90d' / '6w' / ISO-Datum in einen UTC-Zeitpunkt um."""
    if not value:
        return None
    value = value.strip().lower()
    m = re.fullmatch(r"(\d+)([dwm])", value)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        days = {"d": 1, "w": 7, "m": 30}[unit] * n
        return datetime.now(timezone.utc) - timedelta(days=days)
    # sonst als ISO-Datum interpretieren
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def build_signal_text(row: asyncpg.Record) -> str:
    """Baut den zu embeddenden Text aus den relevanten Signal-Feldern."""
    parts: list[str] = []
    for key in ("title", "topic_name", "category", "description", "ai_reason"):
        val = row.get(key)
        if val:
            parts.append(str(val).strip())
    text = "\n\n".join(parts)
    return text[:MAX_TEXT_CHARS]


def to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


async def run(args: argparse.Namespace) -> int:
    cfg = SignaConfig.from_env_write()
    if not cfg.is_configured:
        logger.error(
            "Schreibzugang nicht konfiguriert (TP_ISI_WRITE_USER / TP_ISI_WRITE_SECRET "
            "bzw. TP_ISI_HOST / TP_ISI_DB fehlen)."
        )
        return 2

    since = parse_since(args.since) if not args.all else None

    conditions: list[str] = []
    params: list = []
    idx = 1
    if not args.recompute:
        conditions.append("embedding IS NULL")
    if since is not None:
        conditions.append(f"published_at >= ${idx}::timestamptz")
        params.append(since)
        idx += 1
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    limit_clause = f" LIMIT {int(args.limit)}" if args.limit else ""

    select_sql = f"""
        SELECT id, title, description, ai_reason, topic_name, category
        FROM isi_signals
        {where}
        ORDER BY published_at DESC
        {limit_clause}
    """

    conn = await asyncpg.connect(
        host=cfg.host,
        database=cfg.database,
        user=cfg.user,
        password=cfg.password,
        port=cfg.port,
        timeout=15,
    )
    try:
        rows = await conn.fetch(select_sql, *params)
        total = len(rows)
        logger.info(
            "Gefundene Signale ohne Embedding%s: %d",
            f" seit {since.date()}" if since else " (gesamt)",
            total,
        )
        if total == 0:
            logger.info("Nichts zu tun.")
            return 0
        if args.dry_run:
            logger.info("Dry-Run: keine Embeddings erzeugt, kein Schreibzugriff.")
            for r in rows[:5]:
                preview = build_signal_text(r)[:120].replace("\n", " ")
                logger.info("  #%s %s", r["id"], preview)
            return 0

        done = 0
        for start in range(0, total, args.batch_size):
            batch = rows[start:start + args.batch_size]
            texts = [build_signal_text(r) for r in batch]
            embeddings = embed_texts(texts, batch_size=args.batch_size)

            await conn.executemany(
                "UPDATE isi_signals SET embedding = $2::vector WHERE id = $1",
                [(r["id"], to_vector_literal(emb)) for r, emb in zip(batch, embeddings)],
            )
            done += len(batch)
            logger.info("Fortschritt: %d/%d Embeddings geschrieben", done, total)

        logger.info("Fertig: %d Embeddings (Dim %d) geschrieben.", done, EMBED_DIM)
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="SIGNA Embedding-Backfill")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--since", help="Zeitfenster, z. B. 3m, 90d, 6w oder ISO-Datum")
    group.add_argument("--all", action="store_true", help="Alle Signale (kein Zeitfilter)")
    parser.add_argument("--batch-size", type=int, default=128, help="Embeddings pro Request")
    parser.add_argument("--limit", type=int, default=0, help="Max. Anzahl Signale (0 = ohne Limit)")
    parser.add_argument("--recompute", action="store_true",
                        help="Auch vorhandene Embeddings neu berechnen")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur zählen/vorschauen, nichts schreiben")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

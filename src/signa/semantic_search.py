"""Semantische Suche über SIGNA-Signale (CLI).

Erzeugt ein Query-Embedding (text-embedding-3-large @ 1536), sucht per
Cosine-Distanz die ähnlichsten Signale und gibt das Ergebnis als Markdown
(Obsidian-tauglich) aus – wahlweise nach stdout oder in eine Datei.

Aufruf (aus dem Repo-Root):
    python -m src.signa.semantic_search "Agentische KI in der Hochschullehre" --limit 15
    python src/signa/semantic_search.py "Datenschutz bei LLMs" --since 3m -o kurs.md
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_ENV_FILE = _PROJECT_ROOT / ".env.prod"
if _ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE, override=False)

sys.path.insert(0, str(_PROJECT_ROOT))
from src.signa.embeddings import embed_query  # noqa: E402
from src.signa.embed_backfill import parse_since  # noqa: E402
from src.signa.signa_client import SignaClient  # noqa: E402


def _fmt_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value or "")


def render_markdown(query: str, signals: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    lines: list[str] = [
        f"# SIGNA-Recherche: {query}",
        "",
        f"> Semantische Suche · {len(signals)} Treffer · erzeugt {now} UTC",
        "",
    ]
    for i, s in enumerate(signals, 1):
        sim = s.get("similarity")
        sim_str = f"{sim:.3f}" if isinstance(sim, (int, float)) else "–"
        title = (s.get("title") or "(ohne Titel)").strip()
        url = s.get("url") or ""
        heading = f"## {i}. [{title}]({url})" if url else f"## {i}. {title}"
        lines.append(heading)

        meta = [
            f"**Ähnlichkeit:** {sim_str}",
            f"**Score:** {s.get('total_score', '–')}",
            f"**Datum:** {_fmt_date(s.get('published_at'))}",
        ]
        if s.get("source_name"):
            meta.append(f"**Quelle:** {s['source_name']}")
        if s.get("topic_name"):
            meta.append(f"**Thema:** {s['topic_name']}")
        if s.get("relevant_role"):
            meta.append(f"**Persona:** {s['relevant_role']}")
        lines.append(" · ".join(meta))
        lines.append("")

        reason = (s.get("ai_reason") or "").strip()
        desc = (s.get("description") or "").strip()
        if reason:
            lines.append(f"**Relevanz (KI):** {reason}")
            lines.append("")
        if desc:
            snippet = desc[:600] + ("…" if len(desc) > 600 else "")
            lines.append(snippet)
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> int:
    client = SignaClient()
    if not client.config.is_configured:
        print("FEHLER: SIGNA read-only Zugang nicht konfiguriert (TP_ISI_*).", file=sys.stderr)
        return 2

    since = parse_since(args.since) if args.since else None
    query_vec = embed_query(args.query)

    try:
        signals = await client.semantic_search(
            query_vec,
            min_score=args.min_score,
            type_filter=args.type,
            topic=args.topic,
            persona=args.persona,
            since=since,
            limit=args.limit,
        )
    finally:
        await client.close()

    if not signals:
        print("Keine Treffer. Wurde der Embedding-Backfill bereits ausgeführt?", file=sys.stderr)
        return 1

    md = render_markdown(args.query, signals)
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"{len(signals)} Treffer → {args.output}")
    else:
        print(md)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SIGNA semantische Suche")
    parser.add_argument("query", help="Suchthema / Fragestellung in natürlicher Sprache")
    parser.add_argument("--limit", type=int, default=20, help="Anzahl Treffer")
    parser.add_argument("--min-score", type=float, default=0, help="Mindest-Score (total_score)")
    parser.add_argument("--type", dest="type", help="Filter: type (rss/youtube/web)")
    parser.add_argument("--topic", help="Filter: topic_name")
    parser.add_argument("--persona", help="Filter: relevant_role")
    parser.add_argument("--since", help="Zeitfenster, z. B. 3m, 90d, 6w oder ISO-Datum")
    parser.add_argument("-o", "--output", help="Markdown-Datei (sonst stdout)")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

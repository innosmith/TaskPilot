"""SIGNA Strategic Intelligence Client (async, asyncpg-basiert).

Read-only-Zugriff auf die SIGNA PostgreSQL-Datenbank (Hostinger VPS).
Nutzt einen Connection-Pool für performante Abfragen.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime

import asyncpg

logger = logging.getLogger("taskpilot.signa")

DEFAULT_POOL_MIN = 1
DEFAULT_POOL_MAX = 5


@dataclass
class SignaConfig:
    host: str = ""
    database: str = ""
    user: str = ""
    password: str = ""
    port: int = 5432

    @classmethod
    def from_env(cls) -> "SignaConfig":
        return cls(
            host=os.environ.get("TP_ISI_HOST", os.environ.get("ISI_HOST", "")),
            database=os.environ.get("TP_ISI_DB", os.environ.get("ISI_DB", "")),
            user=os.environ.get("TP_ISI_USER", os.environ.get("ISI_USER", "")),
            password=os.environ.get("TP_ISI_SECRET", os.environ.get("ISI_SECRET", "")),
            port=int(os.environ.get("TP_ISI_PORT", os.environ.get("ISI_PORT", "5432"))),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.database and self.user and self.password)


class SignaClient:
    """Async read-only Client für die SIGNA-Datenbank."""

    def __init__(self, config: SignaConfig | None = None):
        self.config = config or SignaConfig.from_env()
        self._pool: asyncpg.Pool | None = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is None or self._pool._closed:
            self._pool = await asyncpg.create_pool(
                host=self.config.host,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                port=self.config.port,
                min_size=DEFAULT_POOL_MIN,
                max_size=DEFAULT_POOL_MAX,
                timeout=15,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool and not self._pool._closed:
            await self._pool.close()

    # ── Verbindungstest ──────────────────────────────────────

    async def test_connection(self) -> dict:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            count = await conn.fetchval("SELECT count(*) FROM isi_signals")
            return {"ok": True, "version": version, "signal_count": count}

    # ── Signale ──────────────────────────────────────────────

    async def list_signals(
        self,
        limit: int = 30,
        offset: int = 0,
        min_score: float | None = None,
        type_filter: str | None = None,
        topic: str | None = None,
        persona: str | None = None,
        since: "str | datetime | None" = None,
        status_filter: str | None = None,
        search_term: str | None = None,
    ) -> list[dict]:
        pool = await self._ensure_pool()
        conditions: list[str] = []
        params: list = []
        idx = 1

        if min_score is not None:
            conditions.append(f"total_score >= ${idx}")
            params.append(min_score)
            idx += 1
        if type_filter:
            conditions.append(f"type = ${idx}")
            params.append(type_filter)
            idx += 1
        if topic:
            conditions.append(f"topic_name = ${idx}")
            params.append(topic)
            idx += 1
        if persona:
            conditions.append(f"relevant_role = ${idx}")
            params.append(persona)
            idx += 1
        if since:
            since_val = since if isinstance(since, datetime) else datetime.fromisoformat(str(since))
            conditions.append(f"published_at >= ${idx}::timestamptz")
            params.append(since_val)
            idx += 1
        if status_filter:
            conditions.append(f"status = ${idx}")
            params.append(status_filter)
            idx += 1
        if search_term:
            conditions.append(f"(title ILIKE ${idx} OR description ILIKE ${idx})")
            params.append(f"%{search_term}%")
            idx += 1

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)
        params.append(offset)

        query = f"""
            SELECT id, title, source_name, url, type, status, description,
                   thumbnail_url, published_at, total_score, relevant_role,
                   ai_reason, topic_name, category
            FROM isi_signals
            {where}
            ORDER BY published_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    async def count_signals(
        self,
        min_score: float | None = None,
        type_filter: str | None = None,
        topic: str | None = None,
        persona: str | None = None,
        since: "str | datetime | None" = None,
        status_filter: str | None = None,
        search_term: str | None = None,
    ) -> int:
        pool = await self._ensure_pool()
        conditions: list[str] = []
        params: list = []
        idx = 1

        if min_score is not None:
            conditions.append(f"total_score >= ${idx}")
            params.append(min_score)
            idx += 1
        if type_filter:
            conditions.append(f"type = ${idx}")
            params.append(type_filter)
            idx += 1
        if topic:
            conditions.append(f"topic_name = ${idx}")
            params.append(topic)
            idx += 1
        if persona:
            conditions.append(f"relevant_role = ${idx}")
            params.append(persona)
            idx += 1
        if since:
            since_val = since if isinstance(since, datetime) else datetime.fromisoformat(str(since))
            conditions.append(f"published_at >= ${idx}::timestamptz")
            params.append(since_val)
            idx += 1
        if status_filter:
            conditions.append(f"status = ${idx}")
            params.append(status_filter)
            idx += 1
        if search_term:
            conditions.append(f"(title ILIKE ${idx} OR description ILIKE ${idx})")
            params.append(f"%{search_term}%")
            idx += 1

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        async with pool.acquire() as conn:
            return await conn.fetchval(f"SELECT count(*) FROM isi_signals{where}", *params)

    async def get_signal(self, signal_id: int) -> dict | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, title, source_name, url, type, status, description,
                          thumbnail_url, published_at, total_score, relevant_role,
                          ai_reason, topic_name, category, full_content,
                          source_id, "createdAt", "updatedAt"
                   FROM isi_signals WHERE id = $1""",
                signal_id,
            )
            return dict(row) if row else None

    async def search_signals(
        self, query: str, min_score: float = 0, limit: int = 20
    ) -> list[dict]:
        pool = await self._ensure_pool()
        pattern = f"%{query}%"
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, title, source_name, url, type, status, description,
                          thumbnail_url, published_at, total_score, relevant_role,
                          ai_reason, topic_name, category
                   FROM isi_signals
                   WHERE (title ILIKE $1 OR description ILIKE $1 OR full_content ILIKE $1)
                     AND total_score >= $2
                   ORDER BY total_score DESC, published_at DESC
                   LIMIT $3""",
                pattern, min_score, limit,
            )
            return [dict(r) for r in rows]

    # ── Briefings ────────────────────────────────────────────

    async def list_briefings(self, limit: int = 20) -> list[dict]:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, briefing_date, signal_count, high_score_count,
                          avg_score, signal_density, top_keywords, "createdAt"
                   FROM isi_daily_briefings
                   ORDER BY briefing_date DESC LIMIT $1""",
                limit,
            )
            return [dict(r) for r in rows]

    async def get_briefing(self, briefing_id: int) -> dict | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT b.*, p.audio_url, p.duration_seconds, p.status as podcast_status
                   FROM isi_daily_briefings b
                   LEFT JOIN isi_podcast_episodes p ON p.briefing_id = b.id
                   WHERE b.id = $1""",
                briefing_id,
            )
            return dict(row) if row else None

    # ── Deep Dives ───────────────────────────────────────────

    async def list_deep_dives(
        self, persona: str | None = None, limit: int = 20
    ) -> list[dict]:
        pool = await self._ensure_pool()
        if persona:
            rows = await pool.fetch(
                """SELECT id, persona_name, "createdAt", "updatedAt",
                          left(last_synthesis, 300) as preview
                   FROM isi_deep_dives
                   WHERE persona_name = $1
                   ORDER BY "createdAt" DESC LIMIT $2""",
                persona, limit,
            )
        else:
            rows = await pool.fetch(
                """SELECT id, persona_name, "createdAt", "updatedAt",
                          left(last_synthesis, 300) as preview
                   FROM isi_deep_dives
                   ORDER BY "createdAt" DESC LIMIT $1""",
                limit,
            )
        return [dict(r) for r in rows]

    async def get_deep_dive(self, dd_id: int) -> dict | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM isi_deep_dives WHERE id = $1", dd_id
            )
            return dict(row) if row else None

    # ── Stammdaten ───────────────────────────────────────────

    async def list_personas(self) -> list[dict]:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, persona_name, description FROM isi_personas ORDER BY id"
            )
            return [dict(r) for r in rows]

    async def list_topics(self) -> list[dict]:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, topic_name, relevance_weight, category, keywords, strategic_why
                   FROM isi_topics ORDER BY relevance_weight DESC"""
            )
            return [dict(r) for r in rows]

    # ── Statistiken ──────────────────────────────────────────

    async def get_stats(self) -> dict:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    count(*) as total,
                    count(*) FILTER (WHERE total_score >= 8) as high_score,
                    count(*) FILTER (WHERE total_score >= 6 AND total_score < 8) as medium_score,
                    count(*) FILTER (WHERE total_score < 6) as low_score,
                    round(avg(total_score), 2) as avg_score,
                    count(*) FILTER (WHERE published_at >= now() - interval '24 hours') as today,
                    count(*) FILTER (WHERE published_at >= now() - interval '7 days') as this_week,
                    count(DISTINCT source_name) as sources,
                    count(*) FILTER (WHERE type = 'rss') as rss_count,
                    count(*) FILTER (WHERE type = 'youtube') as youtube_count,
                    count(*) FILTER (WHERE type = 'web') as web_count
                FROM isi_signals
            """)
            return dict(row)

"""add agent learning tables (feedback, episodes, learned_rules)

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-14 16:10:00.000000

Fuegt die Self-Learning-Schicht hinzu:
  agent_feedback  -- erfasste Korrektursignale (Draft-Edits, Reklassifikation, Daumen, ...)
  agent_episodes  -- episodisches Gedaechtnis mit lokalem Embedding (pgvector-Recall)
  learned_rules   -- vom Agenten vorgeschlagene, vom Berater freigegebene Regeln
sowie Tone-of-Voice-Felder auf sender_profiles. Identisch zu db/migrations/
005_agent_learning.sql, hier als rohes SQL fuer Paritaet (inkl. pgvector).
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_feedback (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_job_id    UUID REFERENCES agent_jobs(id) ON DELETE SET NULL,
            sender_email    TEXT,
            source          TEXT NOT NULL DEFAULT 'cockpit' CHECK (source IN ('cockpit', 'outlook', 'chat', 'system')),
            feedback_type   TEXT NOT NULL CHECK (feedback_type IN (
                'draft_edit', 'approved_clean', 'rejected',
                'triage_reclass', 'task_deleted', 'task_moved',
                'thumbs_up', 'thumbs_down', 'chat_teach'
            )),
            original        JSONB DEFAULT '{}'::jsonb,
            corrected       JSONB DEFAULT '{}'::jsonb,
            diff_text       TEXT,
            reason          TEXT,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_feedback_job ON agent_feedback(agent_job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_feedback_type ON agent_feedback(feedback_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_feedback_sender ON agent_feedback(sender_email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_feedback_created ON agent_feedback(created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_episodes (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_job_id    UUID REFERENCES agent_jobs(id) ON DELETE SET NULL,
            job_type        TEXT,
            sender_email    TEXT,
            summary         TEXT NOT NULL,
            decision        JSONB DEFAULT '{}'::jsonb,
            was_corrected   BOOLEAN DEFAULT false,
            lesson          TEXT,
            embedding       vector(1024),
            created_at      TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_episodes_job ON agent_episodes(agent_job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_episodes_type ON agent_episodes(job_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_episodes_sender ON agent_episodes(sender_email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_episodes_corrected ON agent_episodes(was_corrected)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_episodes_embedding
            ON agent_episodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learned_rules (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scope           TEXT NOT NULL DEFAULT 'triage' CHECK (scope IN ('triage', 'draft', 'task', 'calendar', 'general')),
            rule_text       TEXT NOT NULL,
            evidence        JSONB DEFAULT '{}'::jsonb,
            status          TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'active', 'rejected', 'archived')),
            autonomy_hint   TEXT,
            created_at      TIMESTAMPTZ DEFAULT now(),
            approved_at     TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_learned_rules_status ON learned_rules(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_learned_rules_scope ON learned_rules(scope)")

    op.execute("ALTER TABLE sender_profiles ADD COLUMN IF NOT EXISTS learned_tone JSONB DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE sender_profiles ADD COLUMN IF NOT EXISTS style_notes TEXT")
    op.execute("ALTER TABLE sender_profiles ADD COLUMN IF NOT EXISTS correction_count INT DEFAULT 0")

    # NOTIFY-Trigger fuer Real-Time-Sichtbarkeit im Cockpit (idempotent).
    op.execute("DROP TRIGGER IF EXISTS agent_feedback_notify ON agent_feedback")
    op.execute(
        """
        CREATE TRIGGER agent_feedback_notify AFTER INSERT OR UPDATE ON agent_feedback
            FOR EACH ROW EXECUTE FUNCTION notify_change('agent_feedback_changed')
        """
    )
    op.execute("DROP TRIGGER IF EXISTS learned_rules_notify ON learned_rules")
    op.execute(
        """
        CREATE TRIGGER learned_rules_notify AFTER INSERT OR UPDATE ON learned_rules
            FOR EACH ROW EXECUTE FUNCTION notify_change('learned_rules_changed')
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS learned_rules_notify ON learned_rules")
    op.execute("DROP TRIGGER IF EXISTS agent_feedback_notify ON agent_feedback")
    op.execute("ALTER TABLE sender_profiles DROP COLUMN IF EXISTS correction_count")
    op.execute("ALTER TABLE sender_profiles DROP COLUMN IF EXISTS style_notes")
    op.execute("ALTER TABLE sender_profiles DROP COLUMN IF EXISTS learned_tone")
    op.execute("DROP TABLE IF EXISTS learned_rules")
    op.execute("DROP TABLE IF EXISTS agent_episodes")
    op.execute("DROP TABLE IF EXISTS agent_feedback")

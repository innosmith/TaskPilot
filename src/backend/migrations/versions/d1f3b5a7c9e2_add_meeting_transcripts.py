"""meeting_transcripts: Teams-Transkripte (Original, Protokoll, Anonymisierung)

Revision ID: d1f3b5a7c9e2
Revises: c9e2a4b6d8f0
Create Date: 2026-07-02 21:10:00.000000

Speichert pro beendetem Teams-Meeting das Original-Transkript (VTT), den
geparsten sprecher-attribuierten Text, das LLM-Protokoll sowie optional die
anonymisierten Fassungen. Die Mapping-Tabelle der Pseudonymisierung bleibt
ausschliesslich lokal in der DB.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd1f3b5a7c9e2'
down_revision: Union[str, Sequence[str], None] = 'c9e2a4b6d8f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS meeting_transcripts (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            meeting_id              TEXT NOT NULL,
            transcript_id           TEXT NOT NULL UNIQUE,
            subject                 TEXT,
            organizer               TEXT,
            started_at              TIMESTAMPTZ,
            ended_at                TIMESTAMPTZ,
            raw_vtt                 TEXT,
            transcript_text         TEXT,
            protocol_md             TEXT,
            anonymized_text         TEXT,
            anonymized_protocol_md  TEXT,
            anonymization_map       JSONB,
            status                  TEXT DEFAULT 'pending'
                CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
            agent_job_id            UUID REFERENCES agent_jobs(id),
            error_message           TEXT,
            created_at              TIMESTAMPTZ DEFAULT now(),
            updated_at              TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meeting_transcripts_status ON meeting_transcripts(status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meeting_transcripts_started ON meeting_transcripts(started_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meeting_transcripts")

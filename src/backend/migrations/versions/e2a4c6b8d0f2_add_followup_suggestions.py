"""followup_suggestions: Dedupe-Anker für die Follow-up-Erkennung

Revision ID: e2a4c6b8d0f2
Revises: d1f3b5a7c9e2
Create Date: 2026-07-02 21:20:00.000000

Eine Zeile pro Sent-Konversation, für die ein Follow-up vorgeschlagen wurde.
Bleibt auch nach Verwerfen des Task-Vorschlags bestehen — verhindert, dass
dieselbe Konversation am nächsten Tag erneut vorgeschlagen wird.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e2a4c6b8d0f2'
down_revision: Union[str, Sequence[str], None] = 'd1f3b5a7c9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS followup_suggestions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id TEXT NOT NULL UNIQUE,
            task_id         UUID REFERENCES tasks(id) ON DELETE SET NULL,
            subject         TEXT,
            recipient       TEXT,
            sent_at         TIMESTAMPTZ,
            status          TEXT DEFAULT 'suggested'
                CHECK (status IN ('suggested', 'answered')),
            created_at      TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_followup_suggestions_status ON followup_suggestions(status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS followup_suggestions")

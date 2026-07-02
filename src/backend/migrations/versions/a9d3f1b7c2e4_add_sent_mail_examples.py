"""add sent_mail_examples (Style-Store fuer Few-Shot-Draft-Anker)

Revision ID: a9d3f1b7c2e4
Revises: c1d2e3f4a5b6
Create Date: 2026-07-02 16:50:00.000000

Lokaler Style-Store: Anthonys gesendete Antworten werden mit lokalem Embedding
(pgvector) indexiert und pro Entwurf als stilistisch/thematisch passende Few-Shot-
Beispiele abgerufen -- auch fuer neue Kontakte ohne History. Bleibt on-prem.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a9d3f1b7c2e4'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_mail_examples (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            graph_id    TEXT UNIQUE NOT NULL,
            recipient   TEXT,
            subject     TEXT,
            body_text   TEXT NOT NULL,
            sent_at     TIMESTAMPTZ,
            language    TEXT,
            embedding   vector(1024),
            created_at  TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_sent_mail_examples_recipient ON sent_mail_examples(recipient)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sent_mail_examples_sent_at ON sent_mail_examples(sent_at DESC)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sent_mail_examples_embedding
            ON sent_mail_examples USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sent_mail_examples")

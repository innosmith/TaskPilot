"""add conversation_context_items (angepinnte Chat-Kontext-Dokumente)

Revision ID: b7e4c9d2a1f8
Revises: a9d3f1b7c2e4
Create Date: 2026-07-02 20:15:00.000000

Angehängte Dokumente (Uploads, OneDrive) werden pro Konversation persistent
«angepinnt»: der extrahierte Volltext wird einmalig gespeichert und bei jedem
weiteren Turn re-injiziert. Behebt den Kontextverlust, bei dem Dokumente nach
der ersten Nachricht für das LLM unsichtbar wurden.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b7e4c9d2a1f8'
down_revision: Union[str, Sequence[str], None] = 'a9d3f1b7c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_context_items (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES llm_conversations(id) ON DELETE CASCADE,
            source_type     TEXT NOT NULL CHECK (source_type IN ('local_upload', 'onedrive_file', 'onedrive_folder')),
            source_ref      TEXT,
            name            TEXT NOT NULL,
            content         TEXT NOT NULL,
            char_count      INT DEFAULT 0,
            pinned          BOOLEAN DEFAULT true,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_context_items_conv "
        "ON conversation_context_items(conversation_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conversation_context_items")

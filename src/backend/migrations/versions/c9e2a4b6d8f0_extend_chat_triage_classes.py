"""chat_triage: 'auto_reply' als gültige Klasse zulassen

Revision ID: c9e2a4b6d8f0
Revises: b7e4c9d2a1f8
Create Date: 2026-07-02 21:00:00.000000

Bugfix: Der Worker mappt 'quick_response' auf 'auto_reply', der CHECK-Constraint
der Tabelle erlaubte aber nur ('task', 'fyi', 'meeting_summary') — das
Zurückschreiben der Klassifikation schlug dann still fehl und die Teams-Triage
blieb ohne persistierte Einordnung.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c9e2a4b6d8f0'
down_revision: Union[str, Sequence[str], None] = 'b7e4c9d2a1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat_triage DROP CONSTRAINT IF EXISTS chat_triage_triage_class_check")
    op.execute(
        "ALTER TABLE chat_triage ADD CONSTRAINT chat_triage_triage_class_check "
        "CHECK (triage_class IN ('task', 'fyi', 'auto_reply', 'meeting_summary'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chat_triage DROP CONSTRAINT IF EXISTS chat_triage_triage_class_check")
    op.execute(
        "ALTER TABLE chat_triage ADD CONSTRAINT chat_triage_triage_class_check "
        "CHECK (triage_class IN ('task', 'fyi', 'meeting_summary'))"
    )

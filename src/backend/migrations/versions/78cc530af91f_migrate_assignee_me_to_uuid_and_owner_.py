"""migrate_assignee_me_to_uuid_and_owner_to_board_members

Revision ID: 78cc530af91f
Revises: 879c21869afc
Create Date: 2026-05-09

Data-Migration:
1. Alle tasks.assignee = 'me' werden auf die UUID des Owner-Users gesetzt.
2. Der Owner wird als BoardMember (role='owner') zu allen Projekten
   hinzugefügt, in denen er noch nicht Mitglied ist.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '78cc530af91f'
down_revision: Union[str, Sequence[str], None] = '879c21869afc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    owner_row = conn.execute(
        sa.text("SELECT id FROM users WHERE role = 'owner' LIMIT 1")
    ).fetchone()
    if not owner_row:
        return
    owner_id = str(owner_row[0])

    conn.execute(
        sa.text("UPDATE tasks SET assignee = :owner_id WHERE assignee = 'me'"),
        {"owner_id": owner_id},
    )

    conn.execute(
        sa.text("""
            INSERT INTO board_members (project_id, user_id, role)
            SELECT p.id, :owner_id, 'member'
            FROM projects p
            WHERE NOT EXISTS (
                SELECT 1 FROM board_members bm
                WHERE bm.project_id = p.id AND bm.user_id = :owner_id
            )
        """),
        {"owner_id": owner_id},
    )


def downgrade() -> None:
    conn = op.get_bind()

    owner_row = conn.execute(
        sa.text("SELECT id FROM users WHERE role = 'owner' LIMIT 1")
    ).fetchone()
    if not owner_row:
        return
    owner_id = str(owner_row[0])

    conn.execute(
        sa.text("UPDATE tasks SET assignee = 'me' WHERE assignee = :owner_id"),
        {"owner_id": owner_id},
    )

    conn.execute(
        sa.text(
            "DELETE FROM board_members WHERE user_id = :owner_id"
        ),
        {"owner_id": owner_id},
    )

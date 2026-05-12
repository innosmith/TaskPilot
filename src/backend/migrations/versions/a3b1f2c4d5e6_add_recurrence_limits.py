"""add_recurrence_limits

Revision ID: a3b1f2c4d5e6
Revises: 78cc530af91f
Create Date: 2026-05-12 22:30:00.000000

Neue Spalten auf tasks: recurrence_end_date, recurrence_max_instances
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a3b1f2c4d5e6'
down_revision: Union[str, Sequence[str], None] = '78cc530af91f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('recurrence_end_date', sa.Date(), nullable=True))
    op.add_column('tasks', sa.Column('recurrence_max_instances', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'recurrence_max_instances')
    op.drop_column('tasks', 'recurrence_end_date')

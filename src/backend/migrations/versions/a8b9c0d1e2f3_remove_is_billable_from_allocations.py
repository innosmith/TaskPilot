"""remove is_billable from capacity_allocations

Revision ID: a8b9c0d1e2f3
Revises: f7c8d9e0a1b2
Create Date: 2026-05-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'f7c8d9e0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('capacity_allocations', 'is_billable')


def downgrade() -> None:
    op.add_column(
        'capacity_allocations',
        sa.Column('is_billable', sa.Boolean(), server_default='true', nullable=False),
    )

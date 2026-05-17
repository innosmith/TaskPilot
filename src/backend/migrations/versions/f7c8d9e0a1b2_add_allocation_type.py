"""add allocation_type to capacity_allocations

Revision ID: f7c8d9e0a1b2
Revises: e5b2c3d4f6a7
Create Date: 2026-05-17 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f7c8d9e0a1b2'
down_revision: Union[str, Sequence[str], None] = 'e5b2c3d4f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'capacity_allocations',
        sa.Column(
            'allocation_type',
            sa.Text(),
            nullable=False,
            server_default='week',
        ),
    )
    op.create_check_constraint(
        'ck_cap_alloc_type',
        'capacity_allocations',
        "allocation_type IN ('week', 'day')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_cap_alloc_type', 'capacity_allocations', type_='check')
    op.drop_column('capacity_allocations', 'allocation_type')

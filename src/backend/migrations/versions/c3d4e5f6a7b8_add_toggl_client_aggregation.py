"""add toggl_client_id and toggl_billable_filter to capacity_projects

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-26 22:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('capacity_projects', sa.Column('toggl_client_id', sa.Integer(), nullable=True))
    op.add_column('capacity_projects', sa.Column('toggl_billable_filter', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('capacity_projects', 'toggl_billable_filter')
    op.drop_column('capacity_projects', 'toggl_client_id')

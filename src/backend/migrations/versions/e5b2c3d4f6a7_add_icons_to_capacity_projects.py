"""add icons to capacity_projects

Revision ID: e5b2c3d4f6a7
Revises: d4a7f1e9c2b3
Create Date: 2026-05-17 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5b2c3d4f6a7'
down_revision: Union[str, Sequence[str], None] = 'd4a7f1e9c2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('capacity_projects', sa.Column('icon_url', sa.Text(), nullable=True))
    op.add_column('capacity_projects', sa.Column('icon_emoji', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('capacity_projects', 'icon_emoji')
    op.drop_column('capacity_projects', 'icon_url')

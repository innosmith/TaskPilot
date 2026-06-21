"""add_finance_analyses_table

Revision ID: f8a9b0c1d2e3
Revises: e6f7a8b9c0d1
Create Date: 2026-06-21 13:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('finance_analyses',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('analysis_type', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('anonymized', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('status', sa.Text(), server_default='completed', nullable=False),
        sa.Column('prompt', sa.Text(), nullable=True),
        sa.Column('report', sa.Text(), nullable=True),
        sa.Column('thinking', sa.Text(), nullable=True),
        sa.Column('snapshot_meta', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=True),
        sa.Column('tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(10, 6), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('completed', 'failed')", name='finance_analyses_status_check'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_finance_analyses_created', 'finance_analyses', [sa.text('created_at DESC')])
    op.create_index('idx_finance_analyses_type', 'finance_analyses', ['analysis_type'])


def downgrade() -> None:
    op.drop_index('idx_finance_analyses_type', table_name='finance_analyses')
    op.drop_index('idx_finance_analyses_created', table_name='finance_analyses')
    op.drop_table('finance_analyses')

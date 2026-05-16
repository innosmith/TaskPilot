"""add capacity planning tables

Revision ID: d4a7f1e9c2b3
Revises: b1236aae31fa
Create Date: 2026-05-17 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd4a7f1e9c2b3'
down_revision: Union[str, Sequence[str], None] = 'b1236aae31fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('capacity_projects',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('color', sa.Text(), nullable=False, server_default='#3B82F6'),
        sa.Column('client_name', sa.Text(), nullable=True),
        sa.Column('hourly_rate', sa.Numeric(10, 2), nullable=True),
        sa.Column('is_billable', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='bestätigt'),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('toggl_project_id', sa.Integer(), nullable=True),
        sa.Column('pipedrive_deal_id', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('bestätigt', 'vorläufig')", name='ck_capacity_projects_status'),
    )
    op.create_index('idx_cap_projects_status', 'capacity_projects', ['status'])
    op.create_index('idx_cap_projects_project', 'capacity_projects', ['project_id'])

    op.create_table('capacity_allocations',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('capacity_project_id', sa.UUID(), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_billable', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('series_id', sa.UUID(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['capacity_project_id'], ['capacity_projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('capacity_project_id', 'week_start', name='uq_cap_alloc_project_week'),
    )
    op.create_index('idx_cap_alloc_week', 'capacity_allocations', ['week_start'])
    op.create_index('idx_cap_alloc_series', 'capacity_allocations', ['series_id'])
    op.create_index('idx_cap_alloc_project', 'capacity_allocations', ['capacity_project_id'])

    op.create_table('capacity_time_off',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False, unique=True),
        sa.Column('type', sa.Text(), server_default='ferien', nullable=False),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('hours', sa.Float(), server_default='8.0', nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("type IN ('ferien', 'feiertag', 'krank', 'sonstiges')", name='ck_capacity_timeoff_type'),
    )
    op.create_index('idx_cap_timeoff_date', 'capacity_time_off', ['date'])

    # Trigger für updated_at
    op.execute("""
        CREATE TRIGGER capacity_projects_updated_at BEFORE UPDATE ON capacity_projects
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    """)
    op.execute("""
        CREATE TRIGGER capacity_allocations_updated_at BEFORE UPDATE ON capacity_allocations
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS capacity_allocations_updated_at ON capacity_allocations;")
    op.execute("DROP TRIGGER IF EXISTS capacity_projects_updated_at ON capacity_projects;")
    op.drop_table('capacity_time_off')
    op.drop_table('capacity_allocations')
    op.drop_table('capacity_projects')

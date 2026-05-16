"""add mindmap tables

Revision ID: b1236aae31fa
Revises: c583be37742c
Create Date: 2026-05-16 23:01:12.472770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b1236aae31fa'
down_revision: Union[str, Sequence[str], None] = 'c583be37742c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('mindmap_folders',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('parent_id', sa.UUID(), nullable=True),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('color', sa.Text(), nullable=True),
        sa.Column('icon_emoji', sa.Text(), nullable=True),
        sa.Column('position', sa.Float(), server_default='0', nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.ForeignKeyConstraint(['parent_id'], ['mindmap_folders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_mindmap_folders_owner', 'mindmap_folders', ['owner_id'])
    op.create_index('idx_mindmap_folders_parent', 'mindmap_folders', ['parent_id'])

    op.create_table('mindmaps',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('folder_id', sa.UUID(), nullable=True),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('visibility', sa.Text(), server_default='private', nullable=False),
        sa.Column('flow_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('background_url', sa.Text(), nullable=True),
        sa.Column('background_color', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.Text(), nullable=True),
        sa.Column('is_template', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['folder_id'], ['mindmap_folders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("visibility IN ('private', 'project', 'shared')", name='ck_mindmaps_visibility'),
    )
    op.create_index('idx_mindmaps_owner', 'mindmaps', ['owner_id'])
    op.create_index('idx_mindmaps_folder', 'mindmaps', ['folder_id'])
    op.create_index('idx_mindmaps_project', 'mindmaps', ['project_id'])
    op.create_index('idx_mindmaps_visibility', 'mindmaps', ['visibility'])

    op.create_table('mindmap_shares',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('mindmap_id', sa.UUID(), nullable=False),
        sa.Column('token', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('permission', sa.Text(), server_default='view', nullable=False),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_used_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['mindmap_id'], ['mindmaps.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
        sa.CheckConstraint("permission IN ('view', 'edit')", name='ck_mindmap_shares_permission'),
    )
    op.create_index('idx_mindmap_shares_mindmap', 'mindmap_shares', ['mindmap_id'])
    op.create_index('idx_mindmap_shares_token', 'mindmap_shares', ['token'])

    op.execute("""
        CREATE TRIGGER mindmap_folders_updated_at BEFORE UPDATE ON mindmap_folders
        FOR EACH ROW EXECUTE FUNCTION update_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER mindmaps_updated_at BEFORE UPDATE ON mindmaps
        FOR EACH ROW EXECUTE FUNCTION update_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER mindmaps_notify AFTER INSERT OR UPDATE OR DELETE ON mindmaps
        FOR EACH ROW EXECUTE FUNCTION notify_change('mindmaps_changed')
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS mindmaps_notify ON mindmaps")
    op.execute("DROP TRIGGER IF EXISTS mindmaps_updated_at ON mindmaps")
    op.execute("DROP TRIGGER IF EXISTS mindmap_folders_updated_at ON mindmap_folders")
    op.drop_index('idx_mindmap_shares_token', table_name='mindmap_shares')
    op.drop_index('idx_mindmap_shares_mindmap', table_name='mindmap_shares')
    op.drop_table('mindmap_shares')
    op.drop_index('idx_mindmaps_visibility', table_name='mindmaps')
    op.drop_index('idx_mindmaps_project', table_name='mindmaps')
    op.drop_index('idx_mindmaps_folder', table_name='mindmaps')
    op.drop_index('idx_mindmaps_owner', table_name='mindmaps')
    op.drop_table('mindmaps')
    op.drop_index('idx_mindmap_folders_parent', table_name='mindmap_folders')
    op.drop_index('idx_mindmap_folders_owner', table_name='mindmap_folders')
    op.drop_table('mindmap_folders')

"""add_notifications_table

Revision ID: c583be37742c
Revises: a3b1f2c4d5e6
Create Date: 2026-05-13 11:49:00.015269

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c583be37742c'
down_revision: Union[str, Sequence[str], None] = 'a3b1f2c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('notifications',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('link', sa.Text(), nullable=True),
        sa.Column('source_type', sa.Text(), nullable=True),
        sa.Column('source_id', sa.UUID(), nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_notifications_user', 'notifications', ['user_id'])
    op.create_index('idx_notifications_created', 'notifications', [sa.text('created_at DESC')])
    op.execute("""
        CREATE INDEX idx_notifications_user_unread
        ON notifications(user_id, is_read)
        WHERE NOT is_read
    """)
    op.execute("""
        CREATE TRIGGER notifications_notify
        AFTER INSERT OR UPDATE ON notifications
        FOR EACH ROW EXECUTE FUNCTION notify_change('notifications_changed')
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS notifications_notify ON notifications")
    op.drop_index('idx_notifications_user_unread', table_name='notifications')
    op.drop_index('idx_notifications_created', table_name='notifications')
    op.drop_index('idx_notifications_user', table_name='notifications')
    op.drop_table('notifications')

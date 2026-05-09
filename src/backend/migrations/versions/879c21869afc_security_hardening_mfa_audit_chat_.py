"""security_hardening_mfa_audit_chat_isolation

Revision ID: 879c21869afc
Revises:
Create Date: 2026-05-09 15:02:34.443122

Neue Spalten auf users (MFA, Einladung), user_id auf llm_conversations,
audit_log-Tabelle, bestehende Conversations dem Owner zuordnen.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '879c21869afc'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- users: MFA-Spalten --
    op.add_column('users', sa.Column('mfa_secret', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('mfa_enabled', sa.Boolean(), server_default='false', nullable=False))

    # -- users: Einladungs-Spalten --
    op.add_column('users', sa.Column('invited_by', sa.UUID(), nullable=True))
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), server_default='false', nullable=False))
    op.create_foreign_key('fk_users_invited_by', 'users', 'users', ['invited_by'], ['id'])

    # -- llm_conversations: User-Isolation --
    op.add_column('llm_conversations', sa.Column('user_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_llm_conversations_user', 'llm_conversations', 'users',
        ['user_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('idx_llm_conversations_user', 'llm_conversations', ['user_id'])

    # Bestehende Conversations dem Owner zuordnen
    op.execute(
        "UPDATE llm_conversations SET user_id = ("
        "  SELECT id FROM users WHERE role = 'owner' LIMIT 1"
        ") WHERE user_id IS NULL"
    )

    # -- audit_log-Tabelle --
    op.create_table(
        'audit_log',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('resource', sa.Text(), nullable=False),
        sa.Column('resource_id', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.Text(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_audit_log_user', 'audit_log', ['user_id'])
    op.create_index('idx_audit_log_created', 'audit_log', [sa.text('created_at DESC')])
    op.create_index('idx_audit_log_action', 'audit_log', ['action'])


def downgrade() -> None:
    op.drop_table('audit_log')

    op.drop_constraint('fk_llm_conversations_user', 'llm_conversations', type_='foreignkey')
    op.drop_index('idx_llm_conversations_user', table_name='llm_conversations')
    op.drop_column('llm_conversations', 'user_id')

    op.drop_constraint('fk_users_invited_by', 'users', type_='foreignkey')
    op.drop_column('users', 'must_change_password')
    op.drop_column('users', 'invited_by')
    op.drop_column('users', 'mfa_enabled')
    op.drop_column('users', 'mfa_secret')

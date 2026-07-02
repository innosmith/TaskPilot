"""extend learned_rules: rule engine (deterministic overrides + scope/skill)

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f6
Create Date: 2026-06-24 19:40:00.000000

Erweitert ``learned_rules`` um die Regel-Engine:
  rule_type        -- 'llm' (Freitext-Leitregel) oder 'deterministic' (Code-Override)
  match_conditions -- Liste [{field, op, value}] (AND), nur deterministisch
  action           -- {triage_class, category, folder}, nur deterministisch
  priority         -- Reihenfolge deterministischer Regeln (kleiner = zuerst)
  applied_count    -- Anwendungszähler (Anzeige/Vertrauen)
Zusätzlich wird der scope-CHECK um 'chat' erweitert, damit Leitregeln auch im
Chat-Kontext (nicht nur Triage) wirken können.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE learned_rules ADD COLUMN IF NOT EXISTS rule_type TEXT NOT NULL DEFAULT 'llm'")
    op.execute("ALTER TABLE learned_rules ADD COLUMN IF NOT EXISTS match_conditions JSONB DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE learned_rules ADD COLUMN IF NOT EXISTS action JSONB DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE learned_rules ADD COLUMN IF NOT EXISTS priority INT DEFAULT 100")
    op.execute("ALTER TABLE learned_rules ADD COLUMN IF NOT EXISTS applied_count INT DEFAULT 0")

    op.execute("ALTER TABLE learned_rules DROP CONSTRAINT IF EXISTS learned_rules_rule_type_check")
    op.execute(
        "ALTER TABLE learned_rules ADD CONSTRAINT learned_rules_rule_type_check "
        "CHECK (rule_type IN ('llm', 'deterministic'))"
    )

    # scope-CHECK um 'chat' erweitern (Leitregeln auch im Chat-Kontext).
    op.execute("ALTER TABLE learned_rules DROP CONSTRAINT IF EXISTS learned_rules_scope_check")
    op.execute(
        "ALTER TABLE learned_rules ADD CONSTRAINT learned_rules_scope_check "
        "CHECK (scope IN ('triage', 'draft', 'task', 'calendar', 'general', 'chat'))"
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_learned_rules_type ON learned_rules(rule_type)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_learned_rules_type")
    op.execute("ALTER TABLE learned_rules DROP CONSTRAINT IF EXISTS learned_rules_scope_check")
    op.execute(
        "ALTER TABLE learned_rules ADD CONSTRAINT learned_rules_scope_check "
        "CHECK (scope IN ('triage', 'draft', 'task', 'calendar', 'general'))"
    )
    op.execute("ALTER TABLE learned_rules DROP CONSTRAINT IF EXISTS learned_rules_rule_type_check")
    op.execute("ALTER TABLE learned_rules DROP COLUMN IF EXISTS applied_count")
    op.execute("ALTER TABLE learned_rules DROP COLUMN IF EXISTS priority")
    op.execute("ALTER TABLE learned_rules DROP COLUMN IF EXISTS action")
    op.execute("ALTER TABLE learned_rules DROP COLUMN IF EXISTS match_conditions")
    op.execute("ALTER TABLE learned_rules DROP COLUMN IF EXISTS rule_type")

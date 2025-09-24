"""Harden workshop_types.active with idempotent SQL"""

from alembic import op
import sqlalchemy as sa


revision = "0075_workshop_type_active_idempotent"
down_revision = "0074_workshop_type_active"
branch_labels = None
depends_on = None


_POSTGRES_STATEMENTS = (
    "ALTER TABLE workshop_types ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE workshop_types ALTER COLUMN active SET DEFAULT TRUE",
    """
    UPDATE workshop_types
       SET active = COALESCE(
         CASE WHEN status IS NOT NULL THEN (LOWER(status) = 'active') END,
         TRUE
       )
     WHERE active IS NULL
    """,
    "ALTER TABLE workshop_types ALTER COLUMN active SET NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_workshop_types_active ON workshop_types(active)",
)


_SQLITE_STATEMENTS = (
    "ALTER TABLE workshop_types ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT 1",
    """
    UPDATE workshop_types
       SET active = COALESCE(
         CASE WHEN status IS NOT NULL THEN (LOWER(status) = 'active') END,
         1
       )
     WHERE active IS NULL
    """,
    "CREATE INDEX IF NOT EXISTS idx_workshop_types_active ON workshop_types(active)",
)


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == "postgresql":
        statements = _POSTGRES_STATEMENTS
    else:
        statements = _SQLITE_STATEMENTS

    for statement in statements:
        conn.execute(sa.text(statement))


def downgrade():
    # Forward-only migration: keep hardened column state.
    pass

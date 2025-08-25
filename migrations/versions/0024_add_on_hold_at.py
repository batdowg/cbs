"""add on_hold_at"""

from alembic import op


revision = '0024_add_on_hold_at'
down_revision = '0023_add_full_name_to_participant_accounts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS on_hold_at TIMESTAMP WITHOUT TIME ZONE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS on_hold_at")

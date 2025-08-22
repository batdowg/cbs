"""add on_hold_at"""

from alembic import op
import sqlalchemy as sa

revision = '0024_add_on_hold_at'
down_revision = '0023_add_full_name_to_participant_accounts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('on_hold_at', sa.DateTime(), nullable=True))
    op.execute("UPDATE sessions SET on_hold_at = CURRENT_TIMESTAMP WHERE on_hold = 1 AND on_hold_at IS NULL")


def downgrade() -> None:
    op.drop_column('sessions', 'on_hold_at')

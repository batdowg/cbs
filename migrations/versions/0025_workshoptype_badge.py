"""add badge to workshop types"""

from alembic import op
import sqlalchemy as sa

revision = '0025_workshoptype_badge'
down_revision = '0024_add_on_hold_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('workshop_types', sa.Column('badge', sa.String(length=50), nullable=True))
    op.execute("UPDATE workshop_types SET badge='Foundations' WHERE badge IS NULL")


def downgrade() -> None:
    op.drop_column('workshop_types', 'badge')

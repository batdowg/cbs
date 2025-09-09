"""add order_date to session_shipping"""

from alembic import op
import sqlalchemy as sa

revision = '0052_add_order_date'
down_revision = '0051_materials_only_and_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('session_shipping', sa.Column('order_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('session_shipping', 'order_date')

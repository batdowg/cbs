"""add fields to session shipping"""

from alembic import op
import sqlalchemy as sa

revision = '0026_session_shipping_fields'
down_revision = '0025_workshoptype_badge'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('session_shipping', sa.Column('arrival_date', sa.Date(), nullable=True))
    op.add_column('session_shipping', sa.Column('order_type', sa.Text(), nullable=True))
    op.add_column('session_shipping', sa.Column('submitted_at', sa.DateTime(), nullable=True))
    op.add_column('session_shipping', sa.Column('delivered_at', sa.DateTime(), nullable=True))
    op.create_unique_constraint('uq_session_shipping_session_id', 'session_shipping', ['session_id'])


def downgrade() -> None:
    op.drop_constraint('uq_session_shipping_session_id', 'session_shipping', type_='unique')
    op.drop_column('session_shipping', 'delivered_at')
    op.drop_column('session_shipping', 'submitted_at')
    op.drop_column('session_shipping', 'order_type')
    op.drop_column('session_shipping', 'arrival_date')

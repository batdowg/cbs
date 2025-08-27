"""add notes to client locations"""

from alembic import op
import sqlalchemy as sa

revision = '0030_location_notes'
down_revision = '0029_client_locations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('client_workshop_locations', sa.Column('access_notes', sa.String(length=255)))
    op.add_column('client_shipping_locations', sa.Column('notes', sa.String(length=255)))


def downgrade() -> None:
    op.drop_column('client_shipping_locations', 'notes')
    op.drop_column('client_workshop_locations', 'access_notes')

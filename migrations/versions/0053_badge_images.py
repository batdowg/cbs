"""add badge_images table"""

from alembic import op
import sqlalchemy as sa

revision = '0053_badge_images'
down_revision = '0052_add_order_date'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'badge_images',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=50), nullable=False, unique=True),
        sa.Column('language', sa.String(length=10), nullable=False, server_default='en'),
        sa.Column('filename', sa.String(length=255), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('badge_images')

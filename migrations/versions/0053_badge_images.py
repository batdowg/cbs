"""add badge image mapping to certificate templates"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0053_badge_images'
down_revision = '0052_add_order_date'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'badge_images',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('language', sa.String(length=8), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
    )
    op.add_column(
        'certificate_templates',
        sa.Column('badge_image_id', sa.Integer, sa.ForeignKey('badge_images.id'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('certificate_templates', 'badge_image_id')
    op.drop_table('badge_images')

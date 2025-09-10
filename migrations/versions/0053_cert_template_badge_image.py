"""noop to backfill missing parent for cert template badge filename"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0053_cert_template_badge_image'
down_revision = '0053_badge_images'
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

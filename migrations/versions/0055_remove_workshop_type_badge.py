"""drop workshop type badge column"""

from alembic import op
import sqlalchemy as sa

revision = '0055_remove_workshop_type_badge'
down_revision = '0054_cert_template_badge_file'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.drop_column('workshop_types', 'badge')

def downgrade() -> None:
    op.add_column('workshop_types', sa.Column('badge', sa.String(length=50), nullable=True))

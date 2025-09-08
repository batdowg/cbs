"""remove default from workshop_type.cert_series"""

from alembic import op
import sqlalchemy as sa

revision = '0047_remove_workshop_type_cert_series_default'
down_revision = '0046_certificate_templates'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column('workshop_types', 'cert_series',
        existing_type=sa.String(length=16),
        server_default=None,
    )


def downgrade() -> None:
    op.alter_column('workshop_types', 'cert_series',
        existing_type=sa.String(length=16),
        server_default='fn',
    )

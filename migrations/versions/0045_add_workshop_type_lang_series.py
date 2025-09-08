"""add supported_languages and cert_series to workshop_types

Revision ID: 0045_add_workshop_type_lang_series
Revises: 0044_add_user_title
Create Date: 2025-09-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0045_add_workshop_type_lang_series'
down_revision = '0044_add_user_title'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('workshop_types')]
    if 'supported_languages' not in cols:
        op.add_column('workshop_types', sa.Column('supported_languages', sa.JSON, nullable=False, server_default='["en"]'))
    if 'cert_series' not in cols:
        op.add_column('workshop_types', sa.Column('cert_series', sa.String(length=16), nullable=False, server_default='fn'))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('workshop_types')]
    if 'cert_series' in cols:
        op.drop_column('workshop_types', 'cert_series')
    if 'supported_languages' in cols:
        op.drop_column('workshop_types', 'supported_languages')

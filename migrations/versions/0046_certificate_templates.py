"""add certificate template series and mappings"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0046_certificate_templates'
down_revision = '0045_add_workshop_type_lang_series'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'certificate_template_series',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('code', sa.String(length=16), nullable=False, unique=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
    )
    op.create_table(
        'certificate_templates',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('series_id', sa.Integer, sa.ForeignKey('certificate_template_series.id', ondelete='CASCADE'), nullable=False),
        sa.Column('language', sa.String(length=8), nullable=False),
        sa.Column('size', sa.String(length=10), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
    )
    op.create_unique_constraint(
        'uix_cert_template_series_lang_size',
        'certificate_templates',
        ['series_id', 'language', 'size'],
    )

def downgrade() -> None:
    op.drop_constraint('uix_cert_template_series_lang_size', 'certificate_templates', type_='unique')
    op.drop_table('certificate_templates')
    op.drop_table('certificate_template_series')

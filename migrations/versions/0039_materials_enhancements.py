"""add materials format/components/po fields"""

from alembic import op
import sqlalchemy as sa


revision = '0039_materials_enhancements'
down_revision = '0038_simulation_outlines'
branch_labels = None
depends_on = None

FORMATS = ('PHYSICAL', 'DIGITAL', 'MIXED', 'SIM_ONLY')


def upgrade() -> None:
    op.add_column(
        'session_shipping',
        sa.Column('materials_format', sa.Enum(*FORMATS, name='materials_format'), nullable=True),
    )
    op.add_column(
        'session_shipping',
        sa.Column('materials_components', sa.JSON(), nullable=True),
    )
    op.add_column(
        'session_shipping', sa.Column('materials_po_number', sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('session_shipping', 'materials_po_number')
    op.drop_column('session_shipping', 'materials_components')
    op.drop_column('session_shipping', 'materials_format')
    sa.Enum(name='materials_format').drop(op.get_bind(), checkfirst=False)

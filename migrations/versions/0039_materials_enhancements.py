"""add materials format/components/po fields"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = '0039_materials_enhancements'
down_revision = '0038_simulation_outlines'
branch_labels = None
depends_on = None

FORMATS = ('PHYSICAL', 'DIGITAL', 'MIXED', 'SIM_ONLY')


def upgrade() -> None:
    fmt_enum = pg.ENUM(*FORMATS, name='materials_format')
    fmt_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'session_shipping',
        sa.Column('materials_format', fmt_enum, nullable=True),
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
    comp_enum = pg.ENUM(name='materials_components')
    fmt_enum = pg.ENUM(name='materials_format')
    comp_enum.drop(op.get_bind(), checkfirst=True)
    fmt_enum.drop(op.get_bind(), checkfirst=True)

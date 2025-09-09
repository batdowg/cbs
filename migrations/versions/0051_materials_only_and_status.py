"""add materials_only flag and materials order fields"""

from alembic import op
import sqlalchemy as sa

revision = '0051_materials_only_and_status'
down_revision = '0049_session_shipping_materials_options'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('materials_only', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('session_shipping', sa.Column('status', sa.String(length=16), nullable=False, server_default='New'))
    op.add_column('session_shipping', sa.Column('material_sets', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('session_shipping', sa.Column('credits', sa.Integer(), nullable=False, server_default='2'))


def downgrade() -> None:
    op.drop_column('session_shipping', 'credits')
    op.drop_column('session_shipping', 'material_sets')
    op.drop_column('session_shipping', 'status')
    op.drop_column('sessions', 'materials_only')

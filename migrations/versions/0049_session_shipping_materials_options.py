"""add session shipping materials options table"""

from alembic import op
import sqlalchemy as sa

revision = '0049_session_shipping_materials_options'
down_revision = '0048_default_materials_option'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'session_shipping_materials_options',
        sa.Column('session_shipping_id', sa.Integer(), nullable=False),
        sa.Column('materials_option_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['session_shipping_id'], ['session_shipping.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['materials_option_id'], ['materials_options.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('session_shipping_id', 'materials_option_id', name='pk_session_shipping_materials_options')
    )


def downgrade() -> None:
    op.drop_table('session_shipping_materials_options')

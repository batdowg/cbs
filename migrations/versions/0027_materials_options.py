"""add materials_options table and session_shipping fields"""

from alembic import op
import sqlalchemy as sa

revision = '0027_materials_options'
down_revision = '0026_session_shipping_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'materials_options',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_type', sa.Text(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('languages', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('formats', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint(
            "order_type IN ('KT-Run Standard materials','KT-Run Modular materials','KT-Run LDI materials','Client-run Bulk order','Simulation')",
            name='ck_materials_options_order_type',
        ),
    )
    op.create_unique_constraint(
        'uq_materials_options_order_type_title',
        'materials_options',
        ['order_type', 'title'],
    )
    op.add_column('session_shipping', sa.Column('name', sa.String(length=120), nullable=False, server_default='Main Shipment'))
    op.add_column('session_shipping', sa.Column('materials_option_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_session_shipping_materials_option',
        'session_shipping',
        'materials_options',
        ['materials_option_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.alter_column('session_shipping', 'name', server_default=None)


def downgrade() -> None:
    op.drop_constraint('fk_session_shipping_materials_option', 'session_shipping', type_='foreignkey')
    op.drop_column('session_shipping', 'materials_option_id')
    op.drop_column('session_shipping', 'name')
    op.drop_constraint('uq_materials_options_order_type_title', 'materials_options', type_='unique')
    op.drop_table('materials_options')

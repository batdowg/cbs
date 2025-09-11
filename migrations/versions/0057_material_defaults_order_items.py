"""add material defaults and order items"""

from alembic import op
import sqlalchemy as sa

revision = '0057_material_defaults_order_items'
down_revision = '0056_cleanup_badge_image_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'materials_options' in insp.get_table_names():
        cols = [c['name'] for c in insp.get_columns('materials_options')]
        if 'description' not in cols:
            op.add_column('materials_options', sa.Column('description', sa.Text(), nullable=True))
        if 'sku_physical' not in cols:
            op.add_column('materials_options', sa.Column('sku_physical', sa.String(length=100), nullable=True))

    if 'material_defaults' not in insp.get_table_names():
        op.create_table(
            'material_defaults',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('workshop_type_id', sa.Integer, sa.ForeignKey('workshop_types.id', ondelete='CASCADE'), nullable=False),
            sa.Column('delivery_type', sa.String(length=32), nullable=False),
            sa.Column('region_code', sa.String(length=8), nullable=False),
            sa.Column('language', sa.String(length=8), nullable=False),
            sa.Column('catalog_ref', sa.String(length=50), nullable=False),
            sa.Column('default_format', sa.String(length=16), nullable=False),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint('workshop_type_id', 'delivery_type', 'region_code', 'language', 'catalog_ref', name='uq_material_defaults_context_ref'),
            sa.CheckConstraint("default_format IN ('Digital','Physical','Self-paced')", name='ck_material_defaults_format'),
        )

    if 'material_order_items' not in insp.get_table_names():
        op.create_table(
            'material_order_items',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('session_id', sa.Integer, sa.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False),
            sa.Column('catalog_ref', sa.String(length=50), nullable=False),
            sa.Column('title_snapshot', sa.String(length=160)),
            sa.Column('description_snapshot', sa.Text()),
            sa.Column('sku_physical_snapshot', sa.String(length=100)),
            sa.Column('language', sa.String(length=8)),
            sa.Column('format', sa.String(length=16)),
            sa.Column('quantity', sa.Integer, nullable=False, server_default='0'),
            sa.Column('processed', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('processed_at', sa.DateTime()),
            sa.Column('processed_by_id', sa.Integer, sa.ForeignKey('users.id', ondelete='SET NULL')),
            sa.CheckConstraint("format IN ('Digital','Physical','Self-paced')", name='ck_material_order_items_format'),
        )
        op.create_index('ix_material_order_items_session_id', 'material_order_items', ['session_id'])
        op.create_index('ix_material_order_items_processed', 'material_order_items', ['processed'])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'material_order_items' in insp.get_table_names():
        op.drop_index('ix_material_order_items_processed', table_name='material_order_items')
        op.drop_index('ix_material_order_items_session_id', table_name='material_order_items')
        op.drop_table('material_order_items')

    if 'material_defaults' in insp.get_table_names():
        op.drop_table('material_defaults')

    if 'materials_options' in insp.get_table_names():
        cols = [c['name'] for c in insp.get_columns('materials_options')]
        if 'sku_physical' in cols:
            op.drop_column('materials_options', 'sku_physical')
        if 'description' in cols:
            op.drop_column('materials_options', 'description')

"""rename material_defaults table"""

from alembic import op
import sqlalchemy as sa

revision = '0058_rename_material_defaults'
down_revision = '0057_material_defaults_order_items'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'material_defaults' in insp.get_table_names():
        op.rename_table('material_defaults', 'workshop_type_material_defaults')
        with op.batch_alter_table('workshop_type_material_defaults') as batch:
            batch.drop_constraint('uq_material_defaults_context_ref', type_='unique')
            batch.drop_constraint('ck_material_defaults_format', type_='check')
            batch.create_unique_constraint(
                'uq_wt_material_defaults_context_ref',
                ['workshop_type_id', 'delivery_type', 'region_code', 'language', 'catalog_ref'],
            )
            batch.create_check_constraint(
                'ck_wt_material_defaults_format',
                "default_format IN ('Digital','Physical','Self-paced')",
            )
    elif 'workshop_type_material_defaults' not in insp.get_table_names():
        op.create_table(
            'workshop_type_material_defaults',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('workshop_type_id', sa.Integer, sa.ForeignKey('workshop_types.id', ondelete='CASCADE'), nullable=False),
            sa.Column('delivery_type', sa.String(length=32), nullable=False),
            sa.Column('region_code', sa.String(length=8), nullable=False),
            sa.Column('language', sa.String(length=8), nullable=False),
            sa.Column('catalog_ref', sa.String(length=50), nullable=False),
            sa.Column('default_format', sa.String(length=16), nullable=False),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint(
                'workshop_type_id', 'delivery_type', 'region_code', 'language', 'catalog_ref',
                name='uq_wt_material_defaults_context_ref',
            ),
            sa.CheckConstraint(
                "default_format IN ('Digital','Physical','Self-paced')",
                name='ck_wt_material_defaults_format',
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'workshop_type_material_defaults' in insp.get_table_names():
        op.rename_table('workshop_type_material_defaults', 'material_defaults')
        with op.batch_alter_table('material_defaults') as batch:
            batch.drop_constraint('uq_wt_material_defaults_context_ref', type_='unique')
            batch.drop_constraint('ck_wt_material_defaults_format', type_='check')
            batch.create_unique_constraint(
                'uq_material_defaults_context_ref',
                ['workshop_type_id', 'delivery_type', 'region_code', 'language', 'catalog_ref'],
            )
            batch.create_check_constraint(
                'ck_material_defaults_format',
                "default_format IN ('Digital','Physical','Self-paced')",
            )

"""add default materials option to workshop types"""

from alembic import op
import sqlalchemy as sa

revision = '0048_default_materials_option'
down_revision = '0047_remove_workshop_type_cert_series_default'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('workshop_types', sa.Column('default_materials_option_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'workshop_types', 'materials_options', ['default_materials_option_id'], ['id'], ondelete='SET NULL')

def downgrade() -> None:
    op.drop_constraint(None, 'workshop_types', type_='foreignkey')
    op.drop_column('workshop_types', 'default_materials_option_id')

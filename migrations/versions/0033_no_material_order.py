revision = '0033_no_material_order'
down_revision = '0032_prework_list_questions'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        'sessions',
        sa.Column('no_material_order', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.alter_column('sessions', 'no_material_order', server_default=None)


def downgrade() -> None:
    op.drop_column('sessions', 'no_material_order')


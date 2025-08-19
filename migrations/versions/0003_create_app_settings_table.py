"""create app_settings table

Revision ID: 0003_create_app_settings_table
Revises: 0002_add_password_hash
Create Date: 2024-05-25
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003_create_app_settings_table'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=120), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    app_settings = sa.table(
        'app_settings',
        sa.column('key', sa.String()),
        sa.column('value', sa.Text()),
    )
    op.bulk_insert(
        app_settings,
        [
            {'key': 'mail.from.prework', 'value': 'certificates@kepner-tregoe.com'},
            {'key': 'mail.from.certificates', 'value': 'certificates@kepner-tregoe.com'},
            {'key': 'mail.from.clientsetup', 'value': 'certificates@kepner-tregoe.com'},
        ],
    )


def downgrade():
    op.drop_table('app_settings')

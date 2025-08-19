"""merge heads

Revision ID: 0004_merge_heads
Revises: 0002, 0003_create_app_settings_table
Create Date: 2024-09-04 00:00:00.000000
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision = '0004_merge_heads'
down_revision = ('0002', '0003_create_app_settings_table')
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass


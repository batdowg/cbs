"""case-insensitive company name unique

Revision ID: 0003_company_unique_lower
Revises: 0002_seed_workshop_types
Create Date: 2024-01-01 00:01:00
"""

from alembic import op
import sqlalchemy as sa

revision = '0003_company_unique_lower'
down_revision = '0002_seed_workshop_types'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.drop_index('ux_company_name', table_name='company')
    op.create_index('ux_company_name_lower', 'company', [sa.text('lower(name)')], unique=True)

def downgrade() -> None:
    op.drop_index('ux_company_name_lower', table_name='company')
    op.create_index('ux_company_name', 'company', ['name'], unique=True)

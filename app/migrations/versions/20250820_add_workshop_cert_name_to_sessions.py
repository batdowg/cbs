"""add workshop_cert_name to sessions

Revision ID: add_workshop_cert_name_20250820
Revises: 
Create Date: 2025-08-20 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_workshop_cert_name_20250820'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # add column if it does not already exist
    conn = op.get_bind()
    has_col = conn.exec_driver_sql("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='sessions' AND column_name='workshop_cert_name'
    """).fetchone()
    if not has_col:
        op.add_column('sessions', sa.Column('workshop_cert_name', sa.Text(), nullable=True))

def downgrade():
    # safe downgrade: drop column if exists
    conn = op.get_bind()
    has_col = conn.exec_driver_sql("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='sessions' AND column_name='workshop_cert_name'
    """).fetchone()
    if has_col:
        op.drop_column('sessions', 'workshop_cert_name')

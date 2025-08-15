"""seed initial workshop types

Revision ID: 0002_seed_workshop_types
Revises: 0001_create_tables
Create Date: 2024-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '0002_seed_workshop_types'
down_revision = '0001_create_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = sa.table(
        'workshop_type',
        sa.column('short_name', sa.String),
        sa.column('full_name', sa.String),
        sa.column('active', sa.Boolean),
    )
    op.bulk_insert(
        table,
        [
            {'short_name': 'PSDM', 'full_name': 'Problem Solving and Decision Making', 'active': True},
            {'short_name': 'PSA', 'full_name': 'Problem Solving App Clinic', 'active': True},
            {'short_name': 'DA', 'full_name': 'Decision Analysis', 'active': True},
            {'short_name': 'SA', 'full_name': 'Situation Appraisal', 'active': True},
            {'short_name': 'PPA', 'full_name': 'Potential Problem Analysis', 'active': True},
        ],
    )


def downgrade() -> None:
    op.execute("delete from workshop_type where short_name in ('PSDM','PSA','DA','SA','PPA')")


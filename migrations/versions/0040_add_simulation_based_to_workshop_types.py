"""add simulation_based to workshop types

Revision ID: 0040_add_simulation_based_to_workshop_types
Revises: 0039_materials_enhancements
Create Date: 2025-??-??
"""

from alembic import op
import sqlalchemy as sa


revision = "0040_add_simulation_based_to_workshop_types"
down_revision = "0039_materials_enhancements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workshop_types",
        sa.Column("simulation_based", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # remove the server default after creation
    op.alter_column("workshop_types", "simulation_based", server_default=None)


def downgrade() -> None:
    op.drop_column("workshop_types", "simulation_based")


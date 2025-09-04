"""rename materials_format values to ALL_PHYSICAL/ALL_DIGITAL

Revision ID: 0041_rename_materials_format_values
Revises: 0040_add_simulation_based_to_workshop_types
Create Date: 2025-??-??
"""

from alembic import op


revision = "0041_rename_materials_format_values"
down_revision = "0040_add_simulation_based_to_workshop_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE materials_format RENAME VALUE 'PHYSICAL' TO 'ALL_PHYSICAL'")
    op.execute("ALTER TYPE materials_format RENAME VALUE 'DIGITAL' TO 'ALL_DIGITAL'")


def downgrade() -> None:
    op.execute("ALTER TYPE materials_format RENAME VALUE 'ALL_PHYSICAL' TO 'PHYSICAL'")
    op.execute("ALTER TYPE materials_format RENAME VALUE 'ALL_DIGITAL' TO 'DIGITAL'")


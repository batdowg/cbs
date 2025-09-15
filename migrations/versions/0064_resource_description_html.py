"""add resource description_html

Revision ID: 0064_resource_description_html
Revises: 0063_remove_default_materials_option
Create Date: 2025-09-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0064_resource_description_html"
down_revision = "0063_remove_default_materials_option"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("description_html", sa.Text()))


def downgrade() -> None:
    op.drop_column("resources", "description_html")


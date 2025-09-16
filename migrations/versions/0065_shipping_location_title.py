"""add title to client shipping locations

Revision ID: 0065_shipping_location_title
Revises: 0064_resource_description_html
Create Date: 2025-09-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0065_shipping_location_title"
down_revision = "0064_resource_description_html"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_shipping_locations",
        sa.Column("title", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_shipping_locations", "title")

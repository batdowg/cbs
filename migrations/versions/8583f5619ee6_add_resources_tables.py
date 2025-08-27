"""add resources tables

Revision ID: 8583f5619ee6
Revises: 0030_location_notes
Create Date: 2025-08-27 20:16:11.331844
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "8583f5619ee6"
down_revision = "0030_location_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("resource_value", sa.String(2048)),
        sa.Column(
            "active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
        ),
    )
    op.create_table(
        "resource_workshop_types",
        sa.Column(
            "resource_id",
            sa.Integer,
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "workshop_type_id",
            sa.Integer,
            sa.ForeignKey("workshop_types.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("resource_workshop_types")
    op.drop_table("resources")


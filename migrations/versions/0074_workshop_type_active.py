"""
Workshop type 'active' flag

Revision ID: 0074_workshop_type_active
Revises: 0073_user_profile_contact_fields
Create Date: 2024-10-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0074_workshop_type_active"
down_revision = "0073_user_profile_contact_fields"
branch_labels = None
depends_on = None


def upgrade():
    """Add boolean 'active' column to workshop_types."""
    op.add_column(
        "workshop_types",
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade():
    """Remove the 'active' column from workshop_types."""
    op.drop_column("workshop_types", "active")

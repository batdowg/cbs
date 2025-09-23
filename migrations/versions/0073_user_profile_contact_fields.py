"""
Revision ID: 0073_user_profile_contact_fields
Revises: 0072_prework_disable_fields
Create Date: 2025-10-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0073_user_profile_contact_fields"
down_revision = "0072_prework_disable_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("state", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(length=120), nullable=True))
    op.add_column(
        "users",
        sa.Column("profile_image_path", sa.String(length=255), nullable=True),
    )

    op.add_column(
        "participant_accounts",
        sa.Column("phone", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "participant_accounts",
        sa.Column("city", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "participant_accounts",
        sa.Column("state", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "participant_accounts",
        sa.Column("country", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "participant_accounts",
        sa.Column("profile_image_path", sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_column("participant_accounts", "profile_image_path")
    op.drop_column("participant_accounts", "country")
    op.drop_column("participant_accounts", "state")
    op.drop_column("participant_accounts", "city")
    op.drop_column("participant_accounts", "phone")

    op.drop_column("users", "profile_image_path")
    op.drop_column("users", "country")
    op.drop_column("users", "state")
    op.drop_column("users", "city")
    op.drop_column("users", "phone")

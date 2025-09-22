"""add number_of_class_days to sessions

Revision ID: 0067_session_number_of_class_days
Revises: 0066_resource_audience_language
Create Date: 2025-09-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0067_session_number_of_class_days"
down_revision = "0066_resource_audience_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "number_of_class_days",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "number_of_class_days")

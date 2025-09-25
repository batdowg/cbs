"""Add company name to session participants

Revision ID: 0078_session_participant_company_name
Revises: 0077_split_names_first_last
Create Date: 2025-01-20 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0078_session_participant_company_name"
down_revision = "0077_split_names_first_last"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "session_participants",
        sa.Column("company_name", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("session_participants", "company_name")


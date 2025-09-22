"""participant attendance table

Revision ID: 0068_participant_attendance
Revises: 0067_session_number_of_class_days
Create Date: 2025-09-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0068_participant_attendance"
down_revision = "0067_session_number_of_class_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participant_attendance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column(
            "attended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "session_id",
            "participant_id",
            "day_index",
            name="uq_participant_attendance_unique",
        ),
    )


def downgrade() -> None:
    op.drop_table("participant_attendance")

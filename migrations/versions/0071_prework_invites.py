"""prework_invites table

Revision ID: 0071_prework_invites
Revises: 0070_prework_template_language
Create Date: 2025-09-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0071_prework_invites"
down_revision = "0070_prework_template_language"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "prework_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sender_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_prework_invites_session_participant",
        "prework_invites",
        ["session_id", "participant_id"],
    )


def downgrade():
    op.drop_index("ix_prework_invites_session_participant", table_name="prework_invites")
    op.drop_table("prework_invites")

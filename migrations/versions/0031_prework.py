"""add prework tables

Revision ID: 0031_prework
Revises: 8583f5619ee6
Create Date: 2025-09-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0031_prework"
down_revision = "8583f5619ee6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prework_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "workshop_type_id",
            sa.Integer,
            sa.ForeignKey("workshop_types.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "require_completion",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("info_html", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
        ),
    )
    op.create_table(
        "prework_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("prework_templates.id", ondelete="CASCADE"),
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "required",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.UniqueConstraint(
            "template_id", "position", name="uq_prework_question_position"
        ),
    )
    op.create_table(
        "prework_template_resources",
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("prework_templates.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "resource_id",
            sa.Integer,
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "prework_assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "participant_account_id",
            sa.Integer,
            sa.ForeignKey("participant_accounts.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("prework_templates.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("snapshot_json", sa.JSON, nullable=False),
        sa.Column("magic_token_hash", sa.String(128)),
        sa.Column("magic_token_expires", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "session_id",
            "participant_account_id",
            name="uq_prework_assignment_unique",
        ),
    )
    op.create_table(
        "prework_answers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Integer,
            sa.ForeignKey("prework_assignments.id", ondelete="CASCADE"),
        ),
        sa.Column("question_index", sa.Integer, nullable=False),
        sa.Column("answer_text", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            onupdate=sa.text("timezone('utc', now())"),
        ),
        sa.UniqueConstraint(
            "assignment_id", "question_index", name="uq_prework_answer_unique"
        ),
    )
    op.create_table(
        "prework_email_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Integer,
            sa.ForeignKey("prework_assignments.id", ondelete="CASCADE"),
        ),
        sa.Column("to_email", sa.String(320)),
        sa.Column("subject", sa.String(255)),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
        ),
    )


def downgrade() -> None:
    op.drop_table("prework_email_log")
    op.drop_table("prework_answers")
    op.drop_table("prework_assignments")
    op.drop_table("prework_template_resources")
    op.drop_table("prework_questions")
    op.drop_table("prework_templates")

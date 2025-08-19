"""core schema baseline for sessions, participants, session_participants, certificates"""

from alembic import op
import sqlalchemy as sa

revision = "0009_core_schema"
down_revision = "0008_add_cert_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # sessions table
    if not inspector.has_table("sessions"):
        op.create_table(
            "sessions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("title", sa.String(255)),
            sa.Column("description", sa.Text),
            sa.Column("client_owner", sa.String(255)),
            sa.Column("start_date", sa.Date),
            sa.Column("end_date", sa.Date),
            sa.Column("location", sa.String(255)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
    else:
        cols = {c["name"] for c in inspector.get_columns("sessions")}
        if "description" not in cols:
            op.add_column("sessions", sa.Column("description", sa.Text))
        if "client_owner" not in cols:
            op.add_column("sessions", sa.Column("client_owner", sa.String(255)))
        if "location" not in cols:
            op.add_column("sessions", sa.Column("location", sa.String(255)))
        if "created_at" not in cols:
            op.add_column(
                "sessions", sa.Column("created_at", sa.DateTime, server_default=sa.func.now())
            )

    # participants table
    if not inspector.has_table("participants"):
        op.create_table(
            "participants",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("full_name", sa.String(255)),
            sa.Column("organization", sa.String(255)),
            sa.Column("job_title", sa.String(255)),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
    else:
        cols = {c["name"] for c in inspector.get_columns("participants")}
        if "organization" not in cols:
            op.add_column("participants", sa.Column("organization", sa.String(255)))
        if "job_title" not in cols:
            op.add_column("participants", sa.Column("job_title", sa.String(255)))
        if "created_at" not in cols:
            op.add_column(
                "participants", sa.Column("created_at", sa.DateTime, server_default=sa.func.now())
            )
        if "cert_name_override" in cols:
            op.drop_column("participants", "cert_name_override")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_participants_email_lower ON participants (LOWER(email))"
    )

    # session_participants table
    if not inspector.has_table("session_participants"):
        op.create_table(
            "session_participants",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "session_id",
                sa.Integer,
                sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            ),
            sa.Column(
                "participant_id",
                sa.Integer,
                sa.ForeignKey("participants.id", ondelete="CASCADE"),
            ),
            sa.UniqueConstraint(
                "session_id", "participant_id", name="uix_session_participant"
            ),
        )
    else:
        uqs = {uc["name"] for uc in inspector.get_unique_constraints("session_participants")}
        if "uix_session_participant" not in uqs:
            op.create_unique_constraint(
                "uix_session_participant",
                "session_participants",
                ["session_id", "participant_id"],
            )

    # certificates table
    if inspector.has_table("certificates"):
        op.drop_table("certificates")

    op.create_table(
        "certificates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "participant_id",
            sa.Integer,
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "session_id",
            sa.Integer,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        ),
        sa.Column("certificate_name", sa.String(255)),
        sa.Column("workshop_name", sa.String(255)),
        sa.Column("workshop_date", sa.Date),
        sa.Column("pdf_path", sa.String(255)),
        sa.Column("issued_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("certificates"):
        op.drop_table("certificates")
    if inspector.has_table("session_participants"):
        op.drop_table("session_participants")
    if inspector.has_table("participants"):
        op.drop_table("participants")
    if inspector.has_table("sessions"):
        op.drop_table("sessions")

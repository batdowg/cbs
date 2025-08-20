"""add session code/timezone and completion_date"""

from alembic import op
import sqlalchemy as sa

revision = "0012_session_code_timezone_completion_date"
down_revision = "0011_user_roles_and_unique_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "sessions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sessions")}
        if "code" not in cols:
            op.add_column("sessions", sa.Column("code", sa.String(50)))
        if "timezone" not in cols:
            op.add_column("sessions", sa.Column("timezone", sa.String(50)))

    if "session_participants" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("session_participants")}
        if "completion_date" not in cols:
            op.add_column("session_participants", sa.Column("completion_date", sa.Date))

    if "certificates" in insp.get_table_names():
        uqs = {uc["name"] for uc in insp.get_unique_constraints("certificates")}
        if "uix_certificate_session_participant" not in uqs:
            op.create_unique_constraint(
                "uix_certificate_session_participant",
                "certificates",
                ["session_id", "participant_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "certificates" in insp.get_table_names():
        uqs = {uc["name"] for uc in insp.get_unique_constraints("certificates")}
        if "uix_certificate_session_participant" in uqs:
            op.drop_constraint(
                "uix_certificate_session_participant", "certificates", type_="unique"
            )

    if "session_participants" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("session_participants")}
        if "completion_date" in cols:
            op.drop_column("session_participants", "completion_date")

    if "sessions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sessions")}
        if "timezone" in cols:
            op.drop_column("sessions", "timezone")
        if "code" in cols:
            op.drop_column("sessions", "code")

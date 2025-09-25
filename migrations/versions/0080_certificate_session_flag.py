"""Add Session.is_certificate_only flag

Revision ID: 0080_certificate_session_flag
Revises: 0079_mail_notification_flags
Create Date: 2025-02-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0080_certificate_session_flag"
down_revision: Union[str, None] = "0079_mail_notification_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_column(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table)}
    if column.name in existing:
        return
    op.add_column(table, column)


def upgrade() -> None:
    column = sa.Column(
        "is_certificate_only",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )
    _ensure_column("sessions", column)

    op.execute(
        sa.text(
            """
            UPDATE sessions
            SET is_certificate_only = COALESCE(is_certificate_only, false)
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sessions" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("sessions")}
    if "is_certificate_only" not in columns:
        return
    op.drop_column("sessions", "is_certificate_only")

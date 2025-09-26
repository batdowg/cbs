"""Add Certificate Manager role flag"""

from alembic import op
import sqlalchemy as sa


revision = "0081_certificate_manager_role"
down_revision = "0080_certificate_session_flag"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "is_certificate_manager" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "is_certificate_manager",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.execute(
            "UPDATE users SET is_certificate_manager = COALESCE(is_certificate_manager, false)"
        )
        op.alter_column(
            "users",
            "is_certificate_manager",
            server_default=None,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "is_certificate_manager" in columns:
        op.drop_column("users", "is_certificate_manager")

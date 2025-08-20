"""ensure users table with roles and lower email unique"""

from alembic import op
import sqlalchemy as sa


revision = "0011_user_roles_and_unique_email"
down_revision = "0010_full_db_from_excel"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "users" not in insp.get_table_names():
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("password_hash", sa.String(255)),
            sa.Column("full_name", sa.String(255)),
            sa.Column("is_app_admin", sa.Boolean, server_default=sa.text("false"), nullable=False),
            sa.Column("is_admin", sa.Boolean, server_default=sa.text("false"), nullable=False),
            sa.Column("is_kcrm", sa.Boolean, server_default=sa.text("false"), nullable=False),
            sa.Column("is_kt_delivery", sa.Boolean, server_default=sa.text("false"), nullable=False),
            sa.Column("is_kt_contractor", sa.Boolean, server_default=sa.text("false"), nullable=False),
            sa.Column("is_kt_staff", sa.Boolean, server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
    else:
        cols = {c["name"] for c in insp.get_columns("users")}

        if "name" in cols and "full_name" not in cols:
            op.alter_column("users", "name", new_column_name="full_name")
            cols.remove("name")
            cols.add("full_name")
        elif "full_name" not in cols:
            op.add_column("users", sa.Column("full_name", sa.String(255)))

        if "password_hash" not in cols:
            op.add_column("users", sa.Column("password_hash", sa.String(255)))

        role_flags = [
            "is_app_admin",
            "is_admin",
            "is_kcrm",
            "is_kt_delivery",
            "is_kt_contractor",
            "is_kt_staff",
        ]
        for flag in role_flags:
            if flag not in cols:
                op.add_column(
                    "users",
                    sa.Column(flag, sa.Boolean, server_default=sa.text("false"), nullable=False),
                )

        if "created_at" not in cols:
            op.add_column(
                "users",
                sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            )

    op.execute("DROP INDEX IF EXISTS ix_users_email")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_lower ON users (lower(email))"
    )


def downgrade():
    pass


from alembic import op
import sqlalchemy as sa

revision = "0018_clients_and_session_links"
down_revision = "0017_session_delivered_flag"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "clients" not in insp.get_table_names():
        op.create_table(
            "clients",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("sfc_link", sa.String(512)),
            sa.Column("crm_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("data_region", sa.String(8)),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_clients_name_lower ON clients (lower(name))"
        )

    if "sessions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sessions")}
        if "client_id" not in cols:
            op.add_column("sessions", sa.Column("client_id", sa.Integer, nullable=True))
            op.create_foreign_key(
                None, "sessions", "clients", ["client_id"], ["id"], ondelete="SET NULL"
            )
        if "csa_account_id" not in cols:
            op.add_column("sessions", sa.Column("csa_account_id", sa.Integer, nullable=True))
            op.create_foreign_key(
                None,
                "sessions",
                "participant_accounts",
                ["csa_account_id"],
                ["id"],
                ondelete="SET NULL",
            )

def downgrade():
    pass

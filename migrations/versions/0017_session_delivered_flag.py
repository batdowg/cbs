from alembic import op
import sqlalchemy as sa

revision = "0017_session_delivered_flag"
down_revision = "0016_participant_accounts_and_session_status"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sessions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sessions")}
        if "delivered" not in cols:
            op.add_column(
                "sessions",
                sa.Column("delivered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            )

def downgrade():
    pass

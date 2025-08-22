from alembic import op
import sqlalchemy as sa

revision = "0019_user_region"
down_revision = "0018_clients_and_session_links"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("users")}
        if "region" not in cols:
            op.add_column("users", sa.Column("region", sa.String(8), nullable=True))


def downgrade():
    pass

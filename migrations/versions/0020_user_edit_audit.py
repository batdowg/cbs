from alembic import op
import sqlalchemy as sa

revision = "0020_user_edit_audit"
down_revision = "0019_user_region"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "user_audit_logs" not in insp.get_table_names():
        op.create_table(
            "user_audit_logs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "actor_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "target_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("field", sa.String(64), nullable=False),
            sa.Column("old_value", sa.String(255)),
            sa.Column("new_value", sa.String(255)),
            sa.Column("changed_at", sa.DateTime, server_default=sa.func.now()),
        )


def downgrade():
    pass

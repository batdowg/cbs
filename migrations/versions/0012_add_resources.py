from alembic import op
import sqlalchemy as sa

revision = "0012_add_resources"
down_revision = "0011_user_roles_and_unique_email"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "resources" not in insp.get_table_names():
        op.create_table(
            "resources",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("type", sa.String(20), nullable=False),
            sa.Column("resource_value", sa.String(2048)),
            sa.Column("active", sa.Boolean, server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_resources_name_lower_active ON resources (lower(name)) WHERE active"
        )

    if "resource_workshop_types" not in insp.get_table_names():
        op.create_table(
            "resource_workshop_types",
            sa.Column(
                "resource_id",
                sa.Integer,
                sa.ForeignKey("resources.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "workshop_type_id",
                sa.Integer,
                sa.ForeignKey("workshop_types.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )


def downgrade():
    pass

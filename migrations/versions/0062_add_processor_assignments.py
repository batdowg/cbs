"""add processor assignments table"""

from alembic import op
import sqlalchemy as sa

revision = "0062_add_processor_assignments"
down_revision = "0061_remove_materials_po_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "processor_assignments" not in insp.get_table_names():
        op.create_table(
            "processor_assignments",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("region", sa.String(length=8), nullable=False),
            sa.Column("processing_type", sa.String(length=20), nullable=False),
            sa.Column(
                "user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
        )
        op.create_unique_constraint(
            "uq_processor_assignment",
            "processor_assignments",
            ["region", "processing_type", "user_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "processor_assignments" in insp.get_table_names():
        op.drop_table("processor_assignments")

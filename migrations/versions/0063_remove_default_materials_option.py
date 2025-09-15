"""remove default materials option from workshop types"""

from alembic import op
import sqlalchemy as sa

revision = "0063_remove_default_materials_option"
down_revision = "0062_add_processor_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("workshop_types", "default_materials_option_id")


def downgrade() -> None:
    op.add_column(
        "workshop_types",
        sa.Column("default_materials_option_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        None,
        "workshop_types",
        "materials_options",
        ["default_materials_option_id"],
        ["id"],
        ondelete="SET NULL",
    )

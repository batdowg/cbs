"""add quantity_basis to materials options"""

from alembic import op
import sqlalchemy as sa

revision = "0060_materials_option_qty_basis"
down_revision = "0059_material_default_qty_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "materials_options" in insp.get_table_names():
        with op.batch_alter_table("materials_options") as batch:
            batch.add_column(
                sa.Column(
                    "quantity_basis",
                    sa.String(length=16),
                    nullable=False,
                    server_default="Per learner",
                )
            )
            batch.create_check_constraint(
                "ck_materials_options_qty_basis",
                "quantity_basis IN ('Per learner','Per order')",
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "materials_options" in insp.get_table_names():
        with op.batch_alter_table("materials_options") as batch:
            batch.drop_constraint("ck_materials_options_qty_basis", type_="check")
            batch.drop_column("quantity_basis")

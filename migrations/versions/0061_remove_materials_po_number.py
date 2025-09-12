"""remove materials_po_number from session shipping"""

from alembic import op
import sqlalchemy as sa

revision = "0061_remove_materials_po_number"
down_revision = "0060_materials_option_qty_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "session_shipping" in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns("session_shipping")]
        if "materials_po_number" in cols:
            with op.batch_alter_table("session_shipping") as batch:
                batch.drop_column("materials_po_number")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "session_shipping" in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns("session_shipping")]
        if "materials_po_number" not in cols:
            with op.batch_alter_table("session_shipping") as batch:
                batch.add_column(sa.Column("materials_po_number", sa.String(length=64)))

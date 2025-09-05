"""cleanup workshop_type short_code leftovers"""

from alembic import op
import sqlalchemy as sa

revision = "0043_cleanup_workshop_type_code"
down_revision = "0042_certificate_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("workshop_types")]
    if "short_code" in cols:
        bind.execute(
            sa.text(
                "UPDATE workshop_types SET code = short_code "
                "WHERE (code IS NULL OR code='') "
                "AND short_code IS NOT NULL AND short_code<>''"
            )
        )
        indexes = [ix["name"] for ix in insp.get_indexes("workshop_types")]
        if "uix_workshop_types_short_code_upper" in indexes:
            op.drop_index(
                "uix_workshop_types_short_code_upper",
                table_name="workshop_types",
            )
        op.drop_column("workshop_types", "short_code")


def downgrade() -> None:
    op.add_column(
        "workshop_types",
        sa.Column("short_code", sa.String(length=16), nullable=True),
    )
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE workshop_types SET short_code = code"))
    op.create_index(
        "uix_workshop_types_short_code_upper",
        "workshop_types",
        [sa.text("upper(short_code)")],
        unique=True,
    )

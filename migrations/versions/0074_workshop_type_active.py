"""
Workshop type 'active' flag

Revision ID: 0074_workshop_type_active
Revises: 0073_user_profile_contact_fields
Create Date: 2024-10-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision = "0074_workshop_type_active"
down_revision = "0073_user_profile_contact_fields"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    """Ensure the workshop_types.active column exists and is populated."""

    columns = _column_names("workshop_types")
    if "active" not in columns:
        op.add_column(
            "workshop_types",
            sa.Column("active", sa.Boolean(), nullable=True),
        )
        columns.add("active")

    wt_active = table("workshop_types", column("active", sa.Boolean()))

    if "status" in columns:
        wt_status = table(
            "workshop_types",
            column("status", sa.String()),
            column("active", sa.Boolean()),
        )
        op.execute(
            wt_status.update()
            .where(wt_status.c.active.is_(None))
            .values(
                active=sa.case(
                    ((sa.func.lower(wt_status.c.status) == "active", sa.true()),),
                    else_=sa.false(),
                )
            )
        )

    op.execute(
        wt_active.update()
        .where(wt_active.c.active.is_(None))
        .values(active=sa.true())
    )

    op.alter_column(
        "workshop_types",
        "active",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.true(),
    )


def downgrade():
    """Remove the 'active' column from workshop_types if it exists."""

    if "active" in _column_names("workshop_types"):
        op.drop_column("workshop_types", "active")

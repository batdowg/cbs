"""split names into first/last columns

Revision ID: 0077_split_names_first_last
Revises: 0076_materials_processor_notifications
Create Date: 2025-01-15 00:00:00.000000
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0077_split_names_first_last"
down_revision = "0076_materials_processor_notifications"
branch_labels = None
depends_on = None


_NAME_RE = re.compile(r"\s*\([^)]*\)")


def _split_name(value: str) -> tuple[str | None, str | None]:
    cleaned = _NAME_RE.sub("", (value or "")).strip()
    if not cleaned:
        return None, None
    parts = cleaned.split()
    if len(parts) == 1:
        return parts[0], None
    first = " ".join(parts[:-1]).strip() or None
    last = parts[-1].strip() or None
    return first, last


def _backfill(table_name: str, id_column: str = "id") -> None:
    connection = op.get_bind()
    table = sa.table(
        table_name,
        sa.column(id_column, sa.Integer),
        sa.column("full_name", sa.String),
        sa.column("first_name", sa.String),
        sa.column("last_name", sa.String),
    )
    rows = connection.execute(
        sa.select(table.c[id_column], table.c.full_name)
        .where(table.c.full_name.isnot(None))
        .where(sa.func.trim(table.c.full_name) != "")
    )
    for row in rows:
        first, last = _split_name(row.full_name)
        updates: dict[str, str] = {}
        if first:
            updates["first_name"] = first[:100]
        if last:
            updates["last_name"] = last[:100]
        if updates:
            connection.execute(
                sa.update(table)
                .where(table.c[id_column] == row[id_column])
                .values(**updates)
            )


def upgrade():
    op.add_column("users", sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=True))
    op.add_column(
        "participants", sa.Column("first_name", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "participants", sa.Column("last_name", sa.String(length=100), nullable=True)
    )

    _backfill("users")
    _backfill("participants")


def downgrade():
    op.drop_column("participants", "last_name")
    op.drop_column("participants", "first_name")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")

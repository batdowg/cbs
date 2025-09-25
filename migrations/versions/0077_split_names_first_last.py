"""split names into first/last columns

Revision ID: 0077_split_names_first_last
Revises: 0076_materials_processor_notifications
Create Date: 2025-01-15 00:00:00.000000
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "0077_split_names_first_last"
down_revision = "0076_materials_processor_notifications"
branch_labels = None
depends_on = None


_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _split_name(value: str | None) -> tuple[str | None, str | None]:
    cleaned = _TRAILING_PAREN_RE.sub("", (value or "")).strip()
    if not cleaned:
        return None, None
    parts = cleaned.split()
    if len(parts) == 1:
        return parts[0], ""
    first = " ".join(parts[:-1]).strip() or None
    last = parts[-1].strip() or None
    return first, last


def _backfill(table_name: str) -> None:
    connection = op.get_bind()
    inspector = inspect(connection)
    columns = inspector.get_columns(table_name)
    if not columns:
        return

    column_map = {column_info["name"]: column_info for column_info in columns}

    id_column_name: str | None = None
    if "id" in column_map:
        id_column_name = "id"
    else:
        for candidate in column_map:
            if candidate.endswith("_id"):
                id_column_name = candidate
                break
    if not id_column_name:
        return

    source_column_name: str | None = None
    for candidate in ("full_name", "name"):
        if candidate in column_map:
            source_column_name = candidate
            break
    if not source_column_name:
        return

    if "first_name" not in column_map or "last_name" not in column_map:
        return

    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=connection)

    id_column = table.c[id_column_name]
    source_column = table.c[source_column_name]
    first_column = table.c.first_name
    last_column = table.c.last_name

    rows = connection.execute(
        sa.select(id_column, source_column)
        .where(source_column.isnot(None))
        .where(sa.func.trim(source_column) != "")
    )
    for row in rows:
        mapping = row._mapping
        first, last = _split_name(mapping[source_column_name])
        updates: dict[str, str] = {}
        if first is not None:
            updates[first_column.name] = first[:100]
        if last is not None:
            updates[last_column.name] = last[:100]
        if updates:
            connection.execute(
                sa.update(table)
                .where(id_column == mapping[id_column_name])
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

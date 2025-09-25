"""add mail notification toggles

Revision ID: 0079_mail_notification_flags
Revises: 0078_participant_company_client
Create Date: 2025-02-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0079_mail_notification_flags"
down_revision: Union[str, None] = "0078_participant_company_client"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_column(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table)}
    if column.name in existing:
        return
    op.add_column(table, column)


def upgrade() -> None:
    columns = [
        sa.Column(
            "notify_account_invite_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "notify_prework_invite_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "notify_materials_processors_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "notify_certificate_delivery_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    ]

    for col in columns:
        _ensure_column("settings", col)

    op.execute(
        sa.text(
            """
            UPDATE settings
            SET
                notify_account_invite_active = COALESCE(notify_account_invite_active, true),
                notify_prework_invite_active = COALESCE(notify_prework_invite_active, true),
                notify_materials_processors_active = COALESCE(notify_materials_processors_active, true),
                notify_certificate_delivery_active = COALESCE(notify_certificate_delivery_active, true)
            """
        )
    )

    for name in (
        "notify_account_invite_active",
        "notify_prework_invite_active",
        "notify_materials_processors_active",
        "notify_certificate_delivery_active",
    ):
        op.alter_column("settings", name, server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "settings" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("settings")}
    for name in (
        "notify_certificate_delivery_active",
        "notify_materials_processors_active",
        "notify_prework_invite_active",
        "notify_account_invite_active",
    ):
        if name in existing:
            op.drop_column("settings", name)

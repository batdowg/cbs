"""add materials processor notification fields

Revision ID: 0076_materials_processor_notifications
Revises: 0075_workshop_type_active_idempotent
Create Date: 2025-01-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0076_materials_processor_notifications"
down_revision = "0075_workshop_type_active_idempotent"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sessions",
        sa.Column("materials_notified_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("materials_order_fingerprint", sa.Text(), nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column(
            "mail_notifications",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        "UPDATE settings SET mail_notifications = '{}'::jsonb WHERE mail_notifications IS NULL"
    )
    op.alter_column(
        "settings",
        "mail_notifications",
        server_default=None,
    )


def downgrade():
    op.drop_column("settings", "mail_notifications")
    op.drop_column("sessions", "materials_order_fingerprint")
    op.drop_column("sessions", "materials_notified_at")

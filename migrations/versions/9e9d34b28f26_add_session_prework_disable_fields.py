"""add session prework disable fields

Revision ID: 9e9d34b28f26
Revises: 0071_prework_invites
Create Date: 2025-09-23 21:30:31.284355
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9e9d34b28f26"
down_revision = "0071_prework_invites"
branch_labels = None
depends_on = None


PREWORK_DISABLE_MODE_ENUM = sa.Enum(
    "notify", "silent", name="prework_disable_mode"
)


def upgrade() -> None:
    bind = op.get_bind()
    PREWORK_DISABLE_MODE_ENUM.create(bind, checkfirst=True)
    op.add_column(
        "sessions",
        sa.Column(
            "prework_disabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.alter_column("sessions", "prework_disabled", server_default=None)
    op.add_column(
        "sessions",
        sa.Column(
            "prework_disable_mode",
            PREWORK_DISABLE_MODE_ENUM,
            nullable=True,
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_column("sessions", "prework_disable_mode")
    op.drop_column("sessions", "prework_disabled")
    PREWORK_DISABLE_MODE_ENUM.drop(bind, checkfirst=True)


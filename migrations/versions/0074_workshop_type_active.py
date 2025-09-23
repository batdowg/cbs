"""
Add workshop_types.active flag.

Revision ID: 0074_workshop_type_active
Revises: 0071_prework_invites
Create Date: 2024-10-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0074_workshop_type_active"
down_revision = "0071_prework_invites"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workshop_types",
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE workshop_types
            SET active = CASE
                WHEN status IS NULL THEN TRUE
                WHEN LOWER(TRIM(status)) = 'active' THEN TRUE
                WHEN LOWER(TRIM(status)) = 'inactive' THEN FALSE
                ELSE TRUE
            END
            """
        )
    )


def downgrade():
    op.drop_column("workshop_types", "active")

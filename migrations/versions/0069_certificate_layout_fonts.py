"""add language allowed fonts and series layout config

Revision ID: 0069_certificate_layout_fonts
Revises: 0068_participant_attendance
Create Date: 2025-09-21 00:00:00.000000
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "0069_certificate_layout_fonts"
down_revision = "0068_participant_attendance"
branch_labels = None
depends_on = None

_DEFAULT_ALLOWED_FONTS = [
    "Times-Italic",
    "Times-Roman",
    "Times-Bold",
    "Helvetica",
    "Helvetica-Bold",
    "Helvetica-Oblique",
]


def upgrade() -> None:
    op.add_column(
        "languages",
        sa.Column(
            "allowed_fonts",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "certificate_template_series",
        sa.Column(
            "layout_config",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE languages SET allowed_fonts = :fonts"),
        {"fonts": json.dumps(_DEFAULT_ALLOWED_FONTS)},
    )

    op.alter_column("languages", "allowed_fonts", server_default=None)
    op.alter_column(
        "certificate_template_series",
        "layout_config",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("certificate_template_series", "layout_config")
    op.drop_column("languages", "allowed_fonts")

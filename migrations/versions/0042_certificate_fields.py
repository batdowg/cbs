"""add certificate fields

Revision ID: 0042_certificate_fields
Revises: 0041_rename_materials_format_values
Create Date: 2025-??-??
"""

from alembic import op
import sqlalchemy as sa

revision = "0042_certificate_fields"
down_revision = "0041_rename_materials_format_values"
branch_labels = None
depends_on = None


PAPER_ENUM = sa.Enum("A4", "LETTER", name="paper_size")
LANG_ENUM = sa.Enum("en", "es", "fr", "ja", "de", "nl", "zh", name="workshop_language")


def upgrade() -> None:
    bind = op.get_bind()
    PAPER_ENUM.create(bind, checkfirst=True)
    LANG_ENUM.create(bind, checkfirst=True)
    op.add_column(
        "sessions",
        sa.Column("paper_size", PAPER_ENUM, nullable=False, server_default="A4"),
    )
    op.add_column(
        "sessions",
        sa.Column("workshop_language", LANG_ENUM, nullable=False, server_default="en"),
    )
    op.execute("UPDATE sessions SET paper_size='A4' WHERE paper_size IS NULL")
    op.execute("UPDATE sessions SET workshop_language='en' WHERE workshop_language IS NULL")
    op.alter_column("sessions", "paper_size", server_default=None)
    op.alter_column("sessions", "workshop_language", server_default=None)


def downgrade() -> None:
    op.drop_column("sessions", "workshop_language")
    op.drop_column("sessions", "paper_size")
    LANG_ENUM.drop(op.get_bind(), checkfirst=True)
    PAPER_ENUM.drop(op.get_bind(), checkfirst=True)

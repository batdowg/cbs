"""add audience and language to resources"""

from alembic import op
import sqlalchemy as sa


revision = "0066_resource_audience_language"
down_revision = "0065_shipping_location_title"
branch_labels = None
depends_on = None


audience_enum = sa.Enum(
    "Participant", "Facilitator", "Both", name="resource_audience"
)


def upgrade() -> None:
    bind = op.get_bind()
    audience_enum.create(bind, checkfirst=True)
    op.add_column(
        "resources",
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
    )
    op.add_column(
        "resources",
        sa.Column(
            "audience",
            audience_enum,
            nullable=False,
            server_default="Participant",
        ),
    )
    op.execute("UPDATE resources SET language = 'en' WHERE language IS NULL OR language = ''")
    op.execute("UPDATE resources SET audience = 'Participant' WHERE audience IS NULL")


def downgrade() -> None:
    op.drop_column("resources", "audience")
    op.drop_column("resources", "language")
    audience_enum.drop(op.get_bind(), checkfirst=True)

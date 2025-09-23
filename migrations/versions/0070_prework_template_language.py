"""add language to prework templates"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0070_prework_template_language"
down_revision = "0069_certificate_layout_fonts"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("prework_templates", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("language", sa.String(length=16), nullable=True, server_default="en")
        )

    op.execute("UPDATE prework_templates SET language = 'en' WHERE language IS NULL")

    with op.batch_alter_table("prework_templates", schema=None) as batch_op:
        batch_op.drop_constraint(
            "prework_templates_workshop_type_id_key", type_="unique"
        )
        batch_op.alter_column(
            "language",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default="en",
        )
        batch_op.create_unique_constraint(
            "uq_prework_template_workshop_language",
            ["workshop_type_id", "language"],
        )


def downgrade():
    with op.batch_alter_table("prework_templates", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_prework_template_workshop_language", type_="unique"
        )
        batch_op.drop_column("language")
        batch_op.create_unique_constraint(
            "prework_templates_workshop_type_id_key", ["workshop_type_id"]
        )


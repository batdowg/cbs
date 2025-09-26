from alembic import op
import sqlalchemy as sa


revision = "0082_certificates_badge_number"
down_revision = "0081_certificate_manager_role"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("certificates")}
    if "certification_number" not in columns:
        op.add_column(
            "certificates",
            sa.Column("certification_number", sa.String(length=64), nullable=True),
        )
        inspector = sa.inspect(bind)

    uniques = {uc["name"] for uc in inspector.get_unique_constraints("certificates")}
    if "uq_certificates_certification_number" not in uniques:
        op.create_unique_constraint(
            "uq_certificates_certification_number",
            "certificates",
            ["certification_number"],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    uniques = {uc["name"] for uc in inspector.get_unique_constraints("certificates")}
    if "uq_certificates_certification_number" in uniques:
        op.drop_constraint(
            "uq_certificates_certification_number",
            "certificates",
            type_="unique",
        )

    columns = {col["name"] for col in inspector.get_columns("certificates")}
    if "certification_number" in columns:
        op.drop_column("certificates", "certification_number")

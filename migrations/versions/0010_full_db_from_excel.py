"""add remaining tables from Excel"""

from alembic import op
import sqlalchemy as sa

revision = "0010_full_db_from_excel"
down_revision = "0009_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # material_types table
    if not inspector.has_table("material_types"):
        op.create_table(
            "material_types",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(100), nullable=False, unique=True, comment="Material type name from Excel"),
        )

    # materials table
    if not inspector.has_table("materials"):
        op.create_table(
            "materials",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("material_type_id", sa.Integer, sa.ForeignKey("material_types.id", ondelete="SET NULL")),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text),
        )
        op.create_index(
            "ix_materials_material_type_id",
            "materials",
            ["material_type_id"],
        )

    # session_shipping table
    if not inspector.has_table("session_shipping"):
        op.create_table(
            "session_shipping",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("session_id", sa.Integer, sa.ForeignKey("sessions.id", ondelete="CASCADE")),
            sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("contact_name", sa.String(255)),
            sa.Column("contact_phone", sa.String(50)),
            sa.Column("contact_email", sa.String(255)),
            sa.Column("address_line1", sa.String(255)),
            sa.Column("address_line2", sa.String(255)),
            sa.Column("city", sa.String(255)),
            sa.Column("state", sa.String(255)),
            sa.Column("postal_code", sa.String(50)),
            sa.Column("country", sa.String(100)),
            sa.Column("courier", sa.String(255)),
            sa.Column("tracking", sa.String(255)),
            sa.Column("ship_date", sa.Date),
            sa.Column("special_instructions", sa.Text),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_session_shipping_session_id",
            "session_shipping",
            ["session_id"],
        )
        op.create_index(
            "ix_session_shipping_created_by",
            "session_shipping",
            ["created_by"],
        )

    # session_shipping_items table
    if not inspector.has_table("session_shipping_items"):
        op.create_table(
            "session_shipping_items",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("session_shipping_id", sa.Integer, sa.ForeignKey("session_shipping.id", ondelete="CASCADE")),
            sa.Column("material_id", sa.Integer, sa.ForeignKey("materials.id", ondelete="SET NULL")),
            sa.Column("quantity", sa.Integer, nullable=False, server_default="0"),
            sa.Column("notes", sa.Text),
        )
        op.create_index(
            "ix_session_shipping_items_session_shipping_id",
            "session_shipping_items",
            ["session_shipping_id"],
        )
        op.create_index(
            "ix_session_shipping_items_material_id",
            "session_shipping_items",
            ["material_id"],
        )

    # badges table
    if not inspector.has_table("badges"):
        op.create_table(
            "badges",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("participant_id", sa.Integer, sa.ForeignKey("participants.id", ondelete="CASCADE")),
            sa.Column("name", sa.String(255), nullable=False, comment="Badge name/type"),
            sa.Column("issued_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_badges_participant_id",
            "badges",
            ["participant_id"],
        )

    # audit_logs table
    if not inspector.has_table("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("session_id", sa.Integer, sa.ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("participant_id", sa.Integer, sa.ForeignKey("participants.id", ondelete="SET NULL"), nullable=True),
            sa.Column("action", sa.String(255), nullable=False),
            sa.Column("details", sa.Text),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_audit_logs_user_id",
            "audit_logs",
            ["user_id"],
        )
        op.create_index(
            "ix_audit_logs_session_id",
            "audit_logs",
            ["session_id"],
        )
        op.create_index(
            "ix_audit_logs_participant_id",
            "audit_logs",
            ["participant_id"],
        )

    # optional seed for material_types
    if inspector.has_table("material_types"):
        op.execute(
            sa.text(
                """
                INSERT INTO material_types (name) VALUES
                    ('book'),
                    ('kit'),
                    ('badge')
                ON CONFLICT (name) DO NOTHING
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in [
        "audit_logs",
        "badges",
        "session_shipping_items",
        "session_shipping",
        "materials",
        "material_types",
    ]:
        if inspector.has_table(table):
            op.drop_table(table)

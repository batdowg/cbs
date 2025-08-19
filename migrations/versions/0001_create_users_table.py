"""create users table

Revision ID: 0001
Revises: 
Create Date: 2024-06-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("is_kt_admin", sa.Boolean(), nullable=True),
        sa.Column("is_kt_crm", sa.Boolean(), nullable=True),
        sa.Column("is_kt_delivery", sa.Boolean(), nullable=True),
        sa.Column("is_kt_contractor", sa.Boolean(), nullable=True),
        sa.Column("is_kt_staff", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")


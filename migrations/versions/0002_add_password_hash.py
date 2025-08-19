"""add password_hash column

Revision ID: 0002
Revises: 0001
Create Date: 2024-06-03 00:00:01.000000
"""

from alembic import op



revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)")
    else:
        op.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE users DROP COLUMN password_hash")
    else:
        op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash")

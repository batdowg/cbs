"""seed smtp defaults

Revision ID: 0005_seed_smtp_defaults
Revises: 0004_merge_heads
Create Date: 2024-09-10
"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '0005_seed_smtp_defaults'
down_revision = '0004_merge_heads'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    defaults = {
        "mail.smtp.host": "smtp.office365.com",
        "mail.smtp.port": "587",
        "mail.smtp.user": "ktbooks@kepner-tregoe.com",
        "mail.from.default": "certificates@kepner-tregoe.com",
        "mail.from.name": "",
    }
    for k, v in defaults.items():
        conn.execute(
            text(
                """
                INSERT INTO app_settings(key, value)
                VALUES (:k, :v)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """
            ),
            {"k": k, "v": v},
        )


def downgrade():
    pass

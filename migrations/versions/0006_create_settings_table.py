"""create settings table

Revision ID: 0006_create_settings_table
Revises: 0005_seed_smtp_defaults
Create Date: 2024-09-30
"""

import os
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '0006_create_settings_table'
down_revision = '0005_seed_smtp_defaults'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            smtp_host VARCHAR(255),
            smtp_port INTEGER,
            smtp_user VARCHAR(255),
            smtp_from_default VARCHAR(255),
            smtp_from_name VARCHAR(255),
            use_tls BOOLEAN DEFAULT TRUE,
            use_ssl BOOLEAN DEFAULT FALSE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn = op.get_bind()
    defaults = {
        'id': 1,
        'smtp_host': os.getenv('SMTP_HOST', 'smtp.office365.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', '587')),
        'smtp_user': os.getenv('SMTP_USER', ''),
        'smtp_from_default': os.getenv('SMTP_FROM_DEFAULT', 'certificates@kepner-tregoe.com'),
        'smtp_from_name': os.getenv('SMTP_FROM_NAME', ''),
    }
    conn.execute(
        text(
            """
            INSERT INTO settings (id, smtp_host, smtp_port, smtp_user, smtp_from_default, smtp_from_name, use_tls, use_ssl)
            VALUES (:id, :smtp_host, :smtp_port, :smtp_user, :smtp_from_default, :smtp_from_name, TRUE, FALSE)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        defaults,
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS settings")

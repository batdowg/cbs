"""seed smtp defaults

Revision ID: 0005_seed_smtp_defaults
Revises: 0004_merge_heads
Create Date: 2024-09-10
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0005_seed_smtp_defaults'
down_revision = '0004_merge_heads'
branch_labels = None
depends_on = None

def upgrade():
    defaults = [
        {'key': 'mail.smtp.host', 'value': 'smtp.office365.com'},
        {'key': 'mail.smtp.port', 'value': '587'},
        {'key': 'mail.smtp.user', 'value': 'ktbooks@kepner-tregoe.com'},
        {'key': 'mail.from.default', 'value': 'certificates@kepner-tregoe.com'},
        {'key': 'mail.from.name', 'value': ''},
    ]
    for row in defaults:
        op.execute(
            sa.text(
                "INSERT INTO app_settings (key, value) VALUES (:key, :value) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            row,
        )


def downgrade():
    keys = [
        'mail.smtp.host',
        'mail.smtp.port',
        'mail.smtp.user',
        'mail.from.default',
        'mail.from.name',
    ]
    for key in keys:
        op.execute(sa.text("DELETE FROM app_settings WHERE key = :key"), {'key': key})

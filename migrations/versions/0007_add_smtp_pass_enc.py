"""add smtp_pass_enc column to settings"""

from alembic import op
import sqlalchemy as sa

revision = '0007_add_smtp_pass_enc'
down_revision = '0006_create_settings_table'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('settings')]
    if 'smtp_pass_enc' not in cols:
        op.add_column('settings', sa.Column('smtp_pass_enc', sa.Text()))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('settings')]
    if 'smtp_pass_enc' in cols:
        op.drop_column('settings', 'smtp_pass_enc')

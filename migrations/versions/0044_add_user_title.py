from alembic import op
import sqlalchemy as sa

revision = '0044_add_user_title'
down_revision = '0043_cleanup_workshop_type_code'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('users')]
    if 'title' not in cols:
        op.add_column('users', sa.Column('title', sa.String(length=255)))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('users')]
    if 'title' in cols:
        op.drop_column('users', 'title')

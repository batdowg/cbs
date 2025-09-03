from alembic import op
import sqlalchemy as sa

revision = '0037_preferred_view'
down_revision = '0036_csa_notify_fields'
branch_labels = None
depends_on = None

VIEWS = ('ADMIN','SESSION_MANAGER','MATERIALS','DELIVERY','LEARNER')

def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'users' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('users')}
        if 'preferred_view' not in cols:
            op.add_column('users', sa.Column('preferred_view', sa.String(20), nullable=True, server_default='ADMIN'))
            op.execute("UPDATE users SET preferred_view='ADMIN' WHERE preferred_view IS NULL")

def downgrade() -> None:
    pass

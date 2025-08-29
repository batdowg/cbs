from alembic import op
import sqlalchemy as sa

revision = '0036_csa_notify_fields'
down_revision = '0035_must_change_password'
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'sessions' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('sessions')}
        if 'csa_notified_account_id' not in cols:
            op.add_column('sessions', sa.Column('csa_notified_account_id', sa.Integer, nullable=True))
            op.create_foreign_key(
                None,
                'sessions',
                'participant_accounts',
                ['csa_notified_account_id'],
                ['id'],
                ondelete='SET NULL'
            )
        if 'csa_notified_at' not in cols:
            op.add_column('sessions', sa.Column('csa_notified_at', sa.DateTime, nullable=True))

def downgrade() -> None:
    pass

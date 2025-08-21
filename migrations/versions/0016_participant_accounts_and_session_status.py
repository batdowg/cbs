import sqlalchemy as sa
from alembic import op

revision = '0016_participant_accounts_and_session_status'
down_revision = '0015_sessions_facilitators_language_participant_title'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'participant_accounts' not in insp.get_table_names():
        op.create_table(
            'participant_accounts',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('password_hash', sa.String(length=255)),
            sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
            sa.Column('last_login', sa.DateTime),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_participant_accounts_email_lower ON participant_accounts (LOWER(email))"
        )

    if 'participants' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('participants')}
        if 'account_id' not in cols:
            op.add_column(
                'participants',
                sa.Column(
                    'account_id',
                    sa.Integer,
                    sa.ForeignKey('participant_accounts.id', ondelete='SET NULL'),
                ),
            )

    if 'sessions' in insp.get_table_names():
        cols = {c['name']: c for c in insp.get_columns('sessions')}
        if 'status' not in cols:
            op.add_column(
                'sessions',
                sa.Column('status', sa.String(length=16), nullable=False, server_default='New'),
            )
        if 'confirmed_ready' not in cols:
            op.add_column(
                'sessions',
                sa.Column(
                    'confirmed_ready',
                    sa.Boolean,
                    nullable=False,
                    server_default=sa.text('false'),
                ),
            )
        if 'daily_start_time' in cols and not cols['daily_start_time'].get('default'):
            op.alter_column('sessions', 'daily_start_time', server_default='08:00:00')
        if 'daily_end_time' in cols and not cols['daily_end_time'].get('default'):
            op.alter_column('sessions', 'daily_end_time', server_default='17:00:00')


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'sessions' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('sessions')}
        if 'confirmed_ready' in cols:
            op.drop_column('sessions', 'confirmed_ready')
        if 'status' in cols:
            op.drop_column('sessions', 'status')
    if 'participants' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('participants')}
        if 'account_id' in cols:
            op.drop_column('participants', 'account_id')
    if 'participant_accounts' in insp.get_table_names():
        op.drop_table('participant_accounts')

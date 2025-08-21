from alembic import op
import sqlalchemy as sa

revision = '0015_sessions_facilitators_language_participant_title'
down_revision = '0014_sessions_fields_fix'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'sessions' in insp.get_table_names():
        cols = {c['name']: c for c in insp.get_columns('sessions')}
        if 'lead_facilitator_id' not in cols:
            op.add_column(
                'sessions',
                sa.Column('lead_facilitator_id', sa.Integer, sa.ForeignKey('users.id', ondelete='SET NULL')),
            )
        if 'language' in cols:
            coltype = cols['language']['type']
            if getattr(coltype, 'length', 0) < 16:
                op.alter_column('sessions', 'language', type_=sa.String(length=16))
        else:
            op.add_column('sessions', sa.Column('language', sa.String(length=16)))

    if 'participants' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('participants')}
        if 'title' not in cols:
            op.add_column('participants', sa.Column('title', sa.String(length=255)))

    if 'session_facilitators' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('session_facilitators')}
        if 'created_at' not in cols:
            op.add_column(
                'session_facilitators',
                sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
            )
    else:
        op.create_table(
            'session_facilitators',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('session_id', sa.Integer, sa.ForeignKey('sessions.id', ondelete='CASCADE')),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE')),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'session_facilitators' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('session_facilitators')}
        if 'created_at' in cols:
            op.drop_column('session_facilitators', 'created_at')

    if 'participants' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('participants')}
        if 'title' in cols:
            op.drop_column('participants', 'title')

    if 'sessions' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('sessions')}
        if 'lead_facilitator_id' in cols:
            op.drop_column('sessions', 'lead_facilitator_id')
        if 'language' in cols:
            op.alter_column('sessions', 'language', type_=sa.String(length=8))

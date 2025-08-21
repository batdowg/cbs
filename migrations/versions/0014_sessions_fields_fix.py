from alembic import op
import sqlalchemy as sa

revision = '0014_sessions_fields_fix'
down_revision = '0013_workshop_types_and_session_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'sessions' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('sessions')}
        if 'daily_start_time' not in cols:
            op.add_column('sessions', sa.Column('daily_start_time', sa.Time()))
        if 'daily_end_time' not in cols:
            op.add_column('sessions', sa.Column('daily_end_time', sa.Time()))
        if 'delivery_type' not in cols:
            op.add_column('sessions', sa.Column('delivery_type', sa.String(length=32)))
        if 'region' not in cols:
            op.add_column('sessions', sa.Column('region', sa.String(length=8)))
        if 'code' in cols:
            op.alter_column('sessions', 'code', type_=sa.String(length=64))

    if 'session_facilitators' not in insp.get_table_names():
        op.create_table(
            'session_facilitators',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('session_id', sa.Integer, sa.ForeignKey('sessions.id', ondelete='CASCADE')),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE')),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'session_facilitators' in insp.get_table_names():
        op.drop_table('session_facilitators')

    if 'sessions' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('sessions')}
        if 'region' in cols:
            op.drop_column('sessions', 'region')
        if 'delivery_type' in cols:
            op.drop_column('sessions', 'delivery_type')
        if 'daily_end_time' in cols:
            op.drop_column('sessions', 'daily_end_time')
        if 'daily_start_time' in cols:
            op.drop_column('sessions', 'daily_start_time')
        if 'code' in cols:
            op.alter_column('sessions', 'code', type_=sa.String(length=50))

from alembic import op
import sqlalchemy as sa

revision = '0013_workshop_types_and_session_fields'
down_revision = '0012_session_code_timezone_completion_date'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'workshop_types' not in insp.get_table_names():
        op.create_table(
            'workshop_types',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('code', sa.String(length=16), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('status', sa.String(length=16), server_default='active'),
            sa.Column('description', sa.Text()),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index(
            'uix_workshop_types_code_upper',
            'workshop_types',
            [sa.text('upper(code)')],
            unique=True,
        )

    if 'sessions' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('sessions')}
        if 'workshop_type_id' not in cols:
            op.add_column('sessions', sa.Column('workshop_type_id', sa.Integer, sa.ForeignKey('workshop_types.id')))
        if 'daily_start_time' not in cols:
            op.add_column('sessions', sa.Column('daily_start_time', sa.Time()))
        if 'daily_end_time' not in cols:
            op.add_column('sessions', sa.Column('daily_end_time', sa.Time()))
        if 'delivery_type' not in cols:
            op.add_column('sessions', sa.Column('delivery_type', sa.String(length=32)))
        if 'language' not in cols:
            op.add_column('sessions', sa.Column('language', sa.String(length=8)))
        if 'capacity' not in cols:
            op.add_column('sessions', sa.Column('capacity', sa.Integer))
        if 'status' not in cols:
            op.add_column('sessions', sa.Column('status', sa.String(length=16)))
        if 'sponsor' not in cols:
            op.add_column('sessions', sa.Column('sponsor', sa.String(length=255)))
        if 'notes' not in cols:
            op.add_column('sessions', sa.Column('notes', sa.Text()))
        if 'simulation_outline' not in cols:
            op.add_column('sessions', sa.Column('simulation_outline', sa.Text()))
        if 'timezone' in cols:
            op.alter_column('sessions', 'timezone', type_=sa.String(length=64))
        if 'start_date' in cols:
            op.alter_column('sessions', 'start_date', type_=sa.Date())
        if 'end_date' in cols:
            op.alter_column('sessions', 'end_date', type_=sa.Date())

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
        if 'simulation_outline' in cols:
            op.drop_column('sessions', 'simulation_outline')
        if 'notes' in cols:
            op.drop_column('sessions', 'notes')
        if 'sponsor' in cols:
            op.drop_column('sessions', 'sponsor')
        if 'status' in cols:
            op.drop_column('sessions', 'status')
        if 'capacity' in cols:
            op.drop_column('sessions', 'capacity')
        if 'language' in cols:
            op.drop_column('sessions', 'language')
        if 'delivery_type' in cols:
            op.drop_column('sessions', 'delivery_type')
        if 'daily_end_time' in cols:
            op.drop_column('sessions', 'daily_end_time')
        if 'daily_start_time' in cols:
            op.drop_column('sessions', 'daily_start_time')
        if 'workshop_type_id' in cols:
            op.drop_column('sessions', 'workshop_type_id')
        if 'timezone' in cols:
            op.alter_column('sessions', 'timezone', type_=sa.String(length=50))

    if 'workshop_types' in insp.get_table_names():
        idx = [ix['name'] for ix in insp.get_indexes('workshop_types')]
        if 'uix_workshop_types_code_upper' in idx:
            op.drop_index('uix_workshop_types_code_upper', table_name='workshop_types')
        op.drop_table('workshop_types')

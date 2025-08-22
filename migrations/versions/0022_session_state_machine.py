from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0022_session_state_machine'
down_revision = '0021_participant_account_certificate_name'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('materials_ordered', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('sessions', sa.Column('ready_for_delivery', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('sessions', sa.Column('info_sent', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('sessions', sa.Column('finalized', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('sessions', sa.Column('on_hold', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('sessions', sa.Column('cancelled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('sessions', sa.Column('materials_ordered_at', sa.DateTime(), nullable=True))
    op.add_column('sessions', sa.Column('ready_at', sa.DateTime(), nullable=True))
    op.add_column('sessions', sa.Column('info_sent_at', sa.DateTime(), nullable=True))
    op.add_column('sessions', sa.Column('delivered_at', sa.DateTime(), nullable=True))
    op.add_column('sessions', sa.Column('finalized_at', sa.DateTime(), nullable=True))
    op.add_column('sessions', sa.Column('cancelled_at', sa.DateTime(), nullable=True))
    op.execute('UPDATE sessions SET materials_ordered=false, ready_for_delivery=false, info_sent=false, finalized=false, on_hold=false, cancelled=false')
    op.create_index('ix_sessions_ready_delivered_cancelled', 'sessions', ['ready_for_delivery', 'delivered', 'cancelled'])
    op.alter_column('sessions', 'materials_ordered', server_default=None)
    op.alter_column('sessions', 'ready_for_delivery', server_default=None)
    op.alter_column('sessions', 'info_sent', server_default=None)
    op.alter_column('sessions', 'finalized', server_default=None)
    op.alter_column('sessions', 'on_hold', server_default=None)
    op.alter_column('sessions', 'cancelled', server_default=None)


def downgrade() -> None:
    op.drop_index('ix_sessions_ready_delivered_cancelled', table_name='sessions')
    op.drop_column('sessions', 'cancelled_at')
    op.drop_column('sessions', 'finalized_at')
    op.drop_column('sessions', 'delivered_at')
    op.drop_column('sessions', 'info_sent_at')
    op.drop_column('sessions', 'ready_at')
    op.drop_column('sessions', 'materials_ordered_at')
    op.drop_column('sessions', 'cancelled')
    op.drop_column('sessions', 'on_hold')
    op.drop_column('sessions', 'finalized')
    op.drop_column('sessions', 'info_sent')
    op.drop_column('sessions', 'ready_for_delivery')
    op.drop_column('sessions', 'materials_ordered')

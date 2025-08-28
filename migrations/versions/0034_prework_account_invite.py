revision = '0034_prework_account_invite'
down_revision = '0033_no_material_order'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        'sessions',
        sa.Column('no_prework', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.alter_column('sessions', 'no_prework', server_default=None)
    op.add_column('participant_accounts', sa.Column('login_magic_hash', sa.String(128), nullable=True))
    op.add_column('participant_accounts', sa.Column('login_magic_expires', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'participant_accounts',
        sa.Column('preferred_language', sa.String(length=10), nullable=False, server_default='en'),
    )
    op.alter_column('participant_accounts', 'preferred_language', server_default=None)
    op.add_column(
        'users',
        sa.Column('preferred_language', sa.String(length=10), nullable=False, server_default='en'),
    )
    op.alter_column('users', 'preferred_language', server_default=None)
    op.add_column('prework_assignments', sa.Column('account_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('prework_assignments', 'account_sent_at')
    op.drop_column('users', 'preferred_language')
    op.drop_column('participant_accounts', 'preferred_language')
    op.drop_column('participant_accounts', 'login_magic_expires')
    op.drop_column('participant_accounts', 'login_magic_hash')
    op.drop_column('sessions', 'no_prework')

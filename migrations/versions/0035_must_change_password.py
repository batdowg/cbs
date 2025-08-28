revision = '0035_must_change_password'
down_revision = '0034_prework_account_invite'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        'participant_accounts',
        sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.alter_column('participant_accounts', 'must_change_password', server_default=None)


def downgrade() -> None:
    op.drop_column('participant_accounts', 'must_change_password')

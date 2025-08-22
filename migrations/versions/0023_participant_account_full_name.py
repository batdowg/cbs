from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0023_participant_account_full_name'
down_revision = '0022_session_state_machine'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('participant_accounts', sa.Column('full_name', sa.String(length=200), nullable=False, server_default=''))
    op.alter_column('participant_accounts', 'full_name', server_default=None)

def downgrade() -> None:
    op.drop_column('participant_accounts', 'full_name')

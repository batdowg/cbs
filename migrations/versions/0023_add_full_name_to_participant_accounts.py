"""add full_name to participant_accounts"""

from alembic import op
import sqlalchemy as sa

revision = '0023_add_full_name_to_participant_accounts'
down_revision = '0022_session_state_machine'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('participant_accounts', sa.Column('full_name', sa.String(length=200), nullable=True))
    op.execute("UPDATE participant_accounts SET full_name = certificate_name WHERE full_name IS NULL")
    op.alter_column('participant_accounts', 'full_name', nullable=False)


def downgrade() -> None:
    op.drop_column('participant_accounts', 'full_name')

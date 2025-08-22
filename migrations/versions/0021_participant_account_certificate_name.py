from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0021_participant_account_certificate_name'
down_revision = '0020_user_edit_audit'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('participant_accounts', sa.Column('certificate_name', sa.String(length=200), server_default='', nullable=False))
    op.execute("UPDATE participant_accounts SET certificate_name='' WHERE certificate_name IS NULL")
    op.alter_column('participant_accounts', 'certificate_name', server_default=None)


def downgrade() -> None:
    op.drop_column('participant_accounts', 'certificate_name')

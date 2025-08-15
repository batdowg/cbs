"""add session access table

Revision ID: 0005_session_access
Revises: 0004_session_learners_shipping
Create Date: 2025-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '0005_session_access'
down_revision = '0004_session_learners_shipping'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_access (
            session_uid uuid REFERENCES session(session_uid) ON DELETE CASCADE,
            user_account_id uuid REFERENCES user_account(user_account_id) ON DELETE CASCADE,
            created_at timestamptz DEFAULT now(),
            PRIMARY KEY (session_uid, user_account_id)
        )
        """
    )

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_access")

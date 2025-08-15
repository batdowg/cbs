"""add session learners and shipping tables and client manager fields

Revision ID: 0004_session_learners_shipping
Revises: 0003_company_unique_lower
Create Date: 2024-08-30 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '0004_session_learners_shipping'
down_revision = '0003_company_unique_lower'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE session ADD COLUMN IF NOT EXISTS client_manager_name text"
    )
    op.execute(
        "ALTER TABLE session ADD COLUMN IF NOT EXISTS client_manager_email text"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_learner (
            learner_uid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            session_uid uuid NOT NULL REFERENCES session(session_uid) ON DELETE CASCADE,
            name text NOT NULL,
            email text NOT NULL,
            created_at timestamptz DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_session_learner_session_uid_lower_email
            ON session_learner (session_uid, lower(email))
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_shipping (
            shipping_uid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            session_uid uuid NOT NULL REFERENCES session(session_uid) ON DELETE CASCADE,
            recipient text,
            address1 text,
            address2 text,
            city text,
            state text,
            postal_code text,
            country text,
            phone text,
            notes text,
            updated_at timestamptz DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_session_shipping_session_uid
            ON session_shipping (session_uid)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_shipping")
    op.execute("DROP TABLE IF EXISTS session_learner")
    op.execute("ALTER TABLE session DROP COLUMN IF EXISTS client_manager_email")
    op.execute("ALTER TABLE session DROP COLUMN IF EXISTS client_manager_name")

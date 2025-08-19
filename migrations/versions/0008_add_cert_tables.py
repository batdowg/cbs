"""add participant and certificate tables"""

from alembic import op
import sqlalchemy as sa

revision = "0008_add_cert_tables"
down_revision = "0007_add_smtp_pass_enc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255),
            start_date DATE,
            end_date DATE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS participants (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            full_name VARCHAR(255),
            cert_name_override VARCHAR(255)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_participants_email_lower ON participants (LOWER(email))"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_participants (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            participant_id INTEGER REFERENCES participants(id) ON DELETE CASCADE,
            UNIQUE(session_id, participant_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS certificates (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            participant_email VARCHAR(255) NOT NULL,
            full_name VARCHAR(255),
            cert_name VARCHAR(255),
            workshop_name VARCHAR(255),
            completion_date DATE,
            file_path VARCHAR(255),
            file_hash VARCHAR(64),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, participant_email)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS certificates")
    op.execute("DROP TABLE IF EXISTS session_participants")
    op.execute("DROP TABLE IF EXISTS participants")
    op.execute("DROP TABLE IF EXISTS sessions")

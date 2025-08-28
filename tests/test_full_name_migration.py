import os
import sys
import sqlalchemy as sa
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import ParticipantAccount


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    with app.app_context():
        yield app
        db.session.remove()


def test_full_name_backfill(app):
    with app.app_context():
        db.session.execute(sa.text(
            """
            CREATE TABLE participant_accounts (
                id INTEGER PRIMARY KEY,
                email VARCHAR(255),
                password_hash VARCHAR(255),
                certificate_name VARCHAR(200),
                login_magic_hash TEXT,
                login_magic_expires DATETIME,
                preferred_language VARCHAR(10) DEFAULT 'en',
                is_active BOOLEAN NOT NULL DEFAULT 1,
                last_login DATETIME,
                created_at DATETIME
            )
            """
        ))
        db.session.execute(
            sa.text(
                "INSERT INTO participant_accounts (id, email, certificate_name, is_active, preferred_language) VALUES (1, 'p@example.com', 'Legacy', 1, 'en')"
            )
        )
        db.session.commit()
        db.session.execute(sa.text("ALTER TABLE participant_accounts ADD COLUMN full_name VARCHAR(200)"))
        db.session.execute(
            sa.text(
                "UPDATE participant_accounts SET full_name = certificate_name WHERE full_name IS NULL"
            )
        )
        db.session.commit()
        acct = db.session.get(ParticipantAccount, 1)
        assert acct.full_name == "Legacy"
        assert acct.full_name is not None

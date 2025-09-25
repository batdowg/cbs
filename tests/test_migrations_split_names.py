import os
from pathlib import Path

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(db_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return config


@pytest.mark.no_smoke
def test_split_names_migration_backfills(tmp_path):
    db_path = tmp_path / "migration.sqlite"
    db_url = f"sqlite:///{db_path}"
    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    config = _alembic_config(db_url)

    command.upgrade(config, "0076_materials_processor_notifications")

    engine = sa.create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (email, full_name) VALUES (:email, :full_name)"
                ),
                {"email": "jane@example.com", "full_name": "Jane Q. Doe"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO users (email, full_name) VALUES (:email, :full_name)"
                ),
                {"email": "mononym@example.com", "full_name": "Prince"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO participants (email, full_name) VALUES (:email, :full_name)"
                ),
                {
                    "email": "legacy@example.com",
                    "full_name": "Mary Ann van Dyke (Learner)",
                },
            )

        command.upgrade(config, "head")

        with engine.connect() as conn:
            user_row = conn.execute(
                sa.text(
                    "SELECT first_name, last_name FROM users WHERE email = :email"
                ),
                {"email": "jane@example.com"},
            ).one()
            assert user_row.first_name == "Jane Q."
            assert user_row.last_name == "Doe"

            mono_row = conn.execute(
                sa.text(
                    "SELECT first_name, last_name FROM users WHERE email = :email"
                ),
                {"email": "mononym@example.com"},
            ).one()
            assert mono_row.first_name == "Prince"
            assert mono_row.last_name is None

            participant_row = conn.execute(
                sa.text(
                    "SELECT first_name, last_name FROM participants WHERE email = :email"
                ),
                {"email": "legacy@example.com"},
            ).one()
            assert participant_row.first_name == "Mary Ann van"
            assert participant_row.last_name == "Dyke"
    finally:
        engine.dispose()
        if original_url is not None:
            os.environ["DATABASE_URL"] = original_url
        else:
            os.environ.pop("DATABASE_URL", None)

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
def test_certificate_session_flag_migration(tmp_path):
    db_path = tmp_path / "migration.sqlite"
    db_url = f"sqlite:///{db_path}"
    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    config = _alembic_config(db_url)

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    engine = sa.create_engine(db_url)
    try:
        with engine.begin() as conn:
            inspector = sa.inspect(conn)
            columns = {col["name"]: col for col in inspector.get_columns("sessions")}
            assert "is_certificate_only" in columns
            column = columns["is_certificate_only"]
            assert not column["nullable"]

            default_clause = column.get("default") or column.get("server_default")
            assert default_clause is not None
            default_text = str(getattr(default_clause, "arg", default_clause)).strip("()'\"")
            assert default_text.lower() in {"false", "0"}

            conn.execute(
                sa.text("INSERT INTO sessions (title) VALUES (:title)"),
                {"title": "Temporary"},
            )
            stored = conn.execute(
                sa.text("SELECT is_certificate_only FROM sessions WHERE title = :title"),
                {"title": "Temporary"},
            ).scalar_one()
            assert stored in (False, 0)
    finally:
        engine.dispose()
        if original_url is not None:
            os.environ["DATABASE_URL"] = original_url
        else:
            os.environ.pop("DATABASE_URL", None)

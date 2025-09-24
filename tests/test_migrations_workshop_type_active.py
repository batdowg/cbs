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
def test_workshop_type_active_migration_idempotent(tmp_path):
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
            columns = {col["name"]: col for col in inspector.get_columns("workshop_types")}
            assert "active" in columns
            active_col = columns["active"]
            assert not active_col["nullable"]

            default_clause = active_col.get("default") or active_col.get("server_default")
            assert default_clause is not None
            default_text = str(getattr(default_clause, "arg", default_clause))
            normalized_default = default_text.strip("()'\"").lower()
            assert normalized_default in {"1", "true"}

            conn.execute(
                sa.text(
                    """
                    INSERT INTO workshop_types (code, name, cert_series, supported_languages)
                    VALUES (:code, :name, :series, :languages)
                    """
                ),
                {
                    "code": "TMP",
                    "name": "Temporary",
                    "series": "fn",
                    "languages": '["en"]',
                },
            )
            wt_id = conn.execute(
                sa.text("SELECT id FROM workshop_types WHERE code = :code"),
                {"code": "TMP"},
            ).scalar_one()

            active_value = conn.execute(
                sa.text("SELECT active FROM workshop_types WHERE id = :id"),
                {"id": wt_id},
            ).scalar_one()
            assert active_value in (True, 1)

            conn.execute(
                sa.text("UPDATE workshop_types SET active = 0 WHERE id = :id"),
                {"id": wt_id},
            )
            toggled = conn.execute(
                sa.text("SELECT active FROM workshop_types WHERE id = :id"),
                {"id": wt_id},
            ).scalar_one()
            assert toggled in (False, 0)
    finally:
        engine.dispose()
        if original_url is not None:
            os.environ["DATABASE_URL"] = original_url
        else:
            os.environ.pop("DATABASE_URL", None)

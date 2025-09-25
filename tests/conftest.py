import os
import pathlib
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.app import create_app, db


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "slow" in item.keywords or "quarantine" in item.keywords:
            continue
        item.add_marker("full")
        if "no_smoke" in item.keywords:
            continue
        item.add_marker("smoke")


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    application = create_app()
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()

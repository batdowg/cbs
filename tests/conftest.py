import os
import pytest

from app.app import create_app, db


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "slow" in item.keywords or "quarantine" in item.keywords:
            continue
        item.add_marker("full")
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

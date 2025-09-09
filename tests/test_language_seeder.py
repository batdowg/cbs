import os
import logging
import pytest

from app.app import create_app, db, seed_languages_safely
from app.models import Language
from app.constants import LANGUAGE_NAMES


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_language_seeder_creates_rows(app):
    with app.app_context():
        seed_languages_safely()
        names = [l.name for l in Language.query.order_by(Language.sort_order).all()]
        assert names == LANGUAGE_NAMES


def test_language_seeder_is_idempotent(app, caplog):
    with app.app_context():
        seed_languages_safely()
        initial = db.session.query(Language).count()
        caplog.set_level(logging.INFO)
        seed_languages_safely()
        after = db.session.query(Language).count()
        assert after == initial == len(LANGUAGE_NAMES)
        assert "Languages already present — skipping." in caplog.text

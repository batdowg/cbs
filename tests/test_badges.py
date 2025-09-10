import os
import sys
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.shared.badges import best_badge_url


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ.setdefault("SITE_ROOT", "/srv")
    os.makedirs(os.environ["SITE_ROOT"], exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_download_badge(app):
    client = app.test_client()
    resp = client.get("/badges/foundations.webp")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "image/webp"
    assert resp.data


def test_best_badge_url_copies_to_site(app):
    site_file = "/srv/badges/foundations.webp"
    if os.path.exists(site_file):
        os.remove(site_file)
    with app.app_context():
        with app.test_request_context():
            url = best_badge_url("Foundations")
            assert url == "/badges/foundations.webp"
    assert os.path.isfile(site_file)


def test_best_badge_respects_site_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SITE_ROOT", str(tmp_path))
    app = create_app()
    with app.app_context():
        db.create_all()
        with app.test_request_context():
            url = best_badge_url("Foundations")
            assert url == "/badges/foundations.webp"
    assert (tmp_path / "badges" / "foundations.webp").is_file()

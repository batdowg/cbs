import os
from io import BytesIO

import pytest

from app.app import create_app, db
from app.models import CertificateTemplateSeries, Language, User


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


@pytest.mark.smoke
def test_upload_cert_template_pdfs(app):
    with app.app_context():
        lang = Language(name="English", sort_order=1)
        series = CertificateTemplateSeries(code="SER", name="Series")
        admin = User(email="admin@example.com", is_admin=True)
        db.session.add_all([lang, series, admin])
        db.session.commit()
        series_id = series.id
        admin_id = admin.id

    client = app.test_client()
    login(client, admin_id)
    data = {
        "files": [
            (BytesIO(b"PDF1"), "file1.pdf"),
            (BytesIO(b"PDF2"), "file2.pdf"),
        ]
    }
    resp = client.post(
        f"/settings/cert-templates/{series_id}/upload-pdfs",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assets_dir = os.path.join(app.root_path, "assets")
    assert os.path.isfile(os.path.join(assets_dir, "file1.pdf"))
    assert os.path.isfile(os.path.join(assets_dir, "file2.pdf"))
    resp = client.get(f"/settings/cert-templates/{series_id}/templates")
    html = resp.data.decode()
    assert "file1.pdf" in html
    assert "file2.pdf" in html


@pytest.mark.smoke
def test_upload_badge_webps(app):
    with app.app_context():
        lang = Language(name="English", sort_order=1)
        series = CertificateTemplateSeries(code="SER", name="Series")
        admin = User(email="admin@example.com", is_admin=True)
        db.session.add_all([lang, series, admin])
        db.session.commit()
        series_id = series.id
        admin_id = admin.id

    client = app.test_client()
    login(client, admin_id)
    data = {"files": [(BytesIO(b"WEBP"), "newbadge.webp")]}
    resp = client.post(
        f"/settings/cert-templates/{series_id}/upload-badges",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    badge_path = os.path.join(app.root_path, "assets", "badges", "newbadge.webp")
    site_path = os.path.join(app.config["SITE_ROOT"], "badges", "newbadge.webp")
    assert os.path.isfile(badge_path)
    assert os.path.isfile(site_path)
    resp = client.get("/badges/newbadge.webp")
    assert resp.status_code == 200
    resp = client.get(f"/settings/cert-templates/{series_id}/templates")
    assert b"newbadge.webp" in resp.data

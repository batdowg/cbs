import io
import os
import pytest

from app.app import create_app, db
from app.models import CertificateTemplate, CertificateTemplateSeries, Language, User
from app.forms.resource_forms import slugify_filename


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv/badges", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


@pytest.mark.smoke
def test_upload_template_persists(app):
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
        "language": "en",
        "size": "A4",
        "file": (io.BytesIO(b"pdf"), "My Template.PDF"),
    }
    resp = client.post(
        f"/settings/cert-templates/{series_id}/upload-template",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    fn = slugify_filename("My Template", "My Template.PDF")
    with app.app_context():
        tmpl = CertificateTemplate.query.filter_by(series_id=series_id, language="en", size="A4").one()
        assert tmpl.filename == fn
        assert os.path.exists(os.path.join(app.root_path, "assets", fn))


@pytest.mark.smoke
def test_upload_badge_persists_and_publish(app):
    with app.app_context():
        lang = Language(name="English", sort_order=1)
        series = CertificateTemplateSeries(code="SER", name="Series")
        tmpl_a4 = CertificateTemplate(series=series, language="en", size="A4", filename="fncert_template_a4_en.pdf")
        tmpl_letter = CertificateTemplate(series=series, language="en", size="LETTER", filename="fncert_template_letter_en.pdf")
        admin = User(email="admin@example.com", is_admin=True)
        db.session.add_all([lang, series, tmpl_a4, tmpl_letter, admin])
        db.session.commit()
        series_id = series.id
        admin_id = admin.id

    client = app.test_client()
    login(client, admin_id)
    data = {
        "language": "en",
        "file": (io.BytesIO(b"webp"), "New Badge.webp"),
    }
    resp = client.post(
        f"/settings/cert-templates/{series_id}/upload-badge",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    fn = slugify_filename("New Badge", "New Badge.webp")
    with app.app_context():
        a4 = CertificateTemplate.query.filter_by(series_id=series_id, language="en", size="A4").one()
        letter = CertificateTemplate.query.filter_by(series_id=series_id, language="en", size="LETTER").one()
        assert a4.badge_filename == fn
        assert letter.badge_filename == fn
        assert os.path.exists(os.path.join(app.root_path, "assets", "badges", fn))
        assert os.path.exists(os.path.join("/srv/badges", fn))

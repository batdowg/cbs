import os

import pytest

from app.app import create_app, db
from app.models import CertificateTemplate, CertificateTemplateSeries, Language, User


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
def test_badge_selection_persists(app):
    with app.app_context():
        lang = Language(name="English", sort_order=1)
        series = CertificateTemplateSeries(code="SER", name="Series")
        tmpl_a4 = CertificateTemplate(
            series=series,
            language="en",
            size="A4",
            filename="fncert_template_a4_en.pdf",
        )
        tmpl_letter = CertificateTemplate(
            series=series,
            language="en",
            size="LETTER",
            filename="fncert_template_letter_en.pdf",
        )
        admin = User(email="admin@example.com", is_admin=True)
        db.session.add_all([lang, series, tmpl_a4, tmpl_letter, admin])
        db.session.commit()
        series_id = series.id
        admin_id = admin.id

    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        f"/settings/cert-templates/{series_id}/templates",
        data={
            "en_A4": "fncert_template_a4_en.pdf",
            "en_LETTER": "fncert_template_letter_en.pdf",
            "badge_en": "foundations.webp",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        a4 = CertificateTemplate.query.filter_by(
            series_id=series_id, language="en", size="A4"
        ).one()
        letter = CertificateTemplate.query.filter_by(
            series_id=series_id, language="en", size="LETTER"
        ).one()
        assert a4.badge_filename == "foundations.webp"
        assert letter.badge_filename == "foundations.webp"

    resp = client.get(f"/settings/cert-templates/{series_id}/templates")
    html = resp.data.decode()
    assert "Badge" in html
    assert 'value="foundations.webp" selected' in html
    assert "/badges/foundations.webp" in html

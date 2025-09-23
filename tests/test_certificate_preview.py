import os

import pytest

from app.app import create_app, db
from app.models import (
    CertificateTemplate,
    CertificateTemplateSeries,
    Language,
    User,
)


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def _seed_series(app, allowed_fonts):
    with app.app_context():
        user = User(email="admin@example.com", is_admin=True)
        user.set_password("pw")
        series = CertificateTemplateSeries(code="series1", name="Preview Series")
        template_a4 = CertificateTemplate(
            series=series,
            language="en",
            size="A4",
            filename="fncert_template_a4_en.pdf",
        )
        template_letter = CertificateTemplate(
            series=series,
            language="en",
            size="LETTER",
            filename="fncert_template_letter_en.pdf",
        )
        language = Language(name="English", allowed_fonts=allowed_fonts)
        db.session.add_all([user, language, series, template_a4, template_letter])
        db.session.commit()
        return user.id, series.id


def test_preview_returns_png(app):
    user_id, series_id = _seed_series(app, ["Helvetica", "Times-Roman"])
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["_csrf_token"] = "token"
    payload = {
        "csrf_token": "token",
        "paper_size": "A4",
        "language": "en",
        "layout": {
            "name": {"font": "Helvetica", "y_mm": 145},
            "workshop": {"font": "Helvetica", "y_mm": 102},
            "date": {"font": "Helvetica", "y_mm": 83},
            "details": {
                "enabled": True,
                "side": "LEFT",
                "variables": ["facilitators", "dates"],
                "size_percent": 90,
            },
        },
    }
    resp = client.post(
        f"/settings/cert-templates/{series_id}/preview",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["image"].startswith("data:image/png;base64,")
    assert isinstance(data["warnings"], list)


def test_preview_emits_font_warning(app):
    user_id, series_id = _seed_series(app, ["Courier"])
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["_csrf_token"] = "token"
    payload = {
        "csrf_token": "token",
        "paper_size": "LETTER",
        "language": "en",
        "layout": {
            "name": {"font": "Helvetica", "y_mm": 145},
            "workshop": {"font": "Helvetica", "y_mm": 102},
            "date": {"font": "Helvetica", "y_mm": 83},
            "details": {"enabled": False, "side": "LEFT", "variables": []},
        },
    }
    resp = client.post(
        f"/settings/cert-templates/{series_id}/preview",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["warnings"], "Expected fallback warnings when fonts are disallowed"
    assert any("Helvetica" in msg for msg in data["warnings"])

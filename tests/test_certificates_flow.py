import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import (
    Certificate,
    CertificateTemplate,
    CertificateTemplateSeries,
    Participant,
    ParticipantAccount,
    Session,
    SessionParticipant,
    User,
    WorkshopType,
)
from app.shared.certificates import render_certificate


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["SITE_ROOT"] = "/srv"
    os.makedirs("/srv/certificates", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def _setup_cert(app):
    with app.app_context():
        series = CertificateTemplateSeries(code="SER", name="Series")
        tmpl = CertificateTemplate(
            series=series,
            language="en",
            size="A4",
            filename="fncert_template_a4_en.pdf",
        )
        wt = WorkshopType(
            code="FOO",
            name="Foo",
            badge="Foundations",
            cert_series="SER",
        )
        sess = Session(title="S1", workshop_type=wt, start_date=date(2024, 1, 1))
        acct = ParticipantAccount(email="p@example.com", full_name="P")
        part = Participant(email="p@example.com", full_name="P", account=acct)
        link = SessionParticipant(
            session=sess, participant=part, completion_date=date(2024, 1, 2)
        )
        admin = User(email="a@example.com", is_admin=True)
        db.session.add_all([series, tmpl, wt, sess, acct, part, link, admin])
        db.session.commit()
        render_certificate(sess, acct)
        cert = Certificate.query.filter_by(session_id=sess.id, participant_id=part.id).one()
        return sess, part, acct, cert, admin


def test_generation_stores_session_path(app):
    sess, part, acct, cert, _ = _setup_cert(app)
    year = sess.start_date.year
    assert cert.pdf_path.startswith(f"{year}/{sess.id}/")
    assert os.path.isfile(os.path.join("/srv/certificates", cert.pdf_path))


def test_download_success_and_missing_file(app, caplog):
    sess, part, acct, cert, _ = _setup_cert(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s["participant_account_id"] = acct.id
    resp = client.get(f"/certificates/{cert.id}")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    os.remove(os.path.join("/srv/certificates", cert.pdf_path))
    caplog.set_level("WARNING")
    resp = client.get(f"/certificates/{cert.id}")
    assert resp.status_code == 404
    assert "[CERT-MISSING]" in caplog.text


def test_badge_image_and_label(app):
    sess, part, acct, cert, admin = _setup_cert(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = admin.id
    resp = client.get(f"/sessions/{sess.id}")
    html = resp.data.decode()
    assert '<img src="/badges/foundations.webp"' in html
    assert "Badge" in html
    assert "Download Certificate" in html


def test_badge_label_without_image(app):
    sess, part, acct, cert, admin = _setup_cert(app)
    sess.workshop_type.badge = "Imaginary"
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = admin.id
    resp = client.get(f"/sessions/{sess.id}")
    html = resp.data.decode()
    assert "Badge" in html
    assert "<img" not in html

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
    ParticipantAttendance,
    Session,
    SessionParticipant,
    User,
    WorkshopType,
)
from app.shared.certificates import (
    CertificateAttendanceError,
    render_certificate,
    render_for_session,
    resolve_series_template,
)


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


def test_resolve_series_template_uses_explicit_mapping(app, caplog):
    with app.app_context():
        caplog.set_level("INFO")
        series = CertificateTemplateSeries(code="SER1", name="Series 1")
        mapping = CertificateTemplate(
            series=series,
            language="en",
            size="LETTER",
            filename="custom_letter.pdf",
        )
        db.session.add_all([series, mapping])
        db.session.commit()
        assets_dir = os.path.join(app.root_path, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        custom_path = os.path.join(assets_dir, "custom_letter.pdf")
        with open(custom_path, "wb") as handle:
            handle.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\nstartxref\n0\n%%EOF")
        try:
            resolution = resolve_series_template(series.id, "LETTER", "en")
            assert resolution.path == custom_path
            assert resolution.source == "explicit"
            assert "source=explicit" in caplog.text
        finally:
            os.remove(custom_path)


def test_resolve_series_template_falls_back_to_pattern(app, caplog):
    with app.app_context():
        caplog.set_level("INFO")
        series = CertificateTemplateSeries(code="SER2", name="Series 2")
        mapping = CertificateTemplate(
            series=series,
            language="zz",
            size="LETTER",
            filename="missing_letter.pdf",
        )
        db.session.add_all([series, mapping])
        db.session.commit()
        assets_dir = os.path.join(app.root_path, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        pattern_name = "fncert_template_letter_zz.pdf"
        pattern_path = os.path.join(assets_dir, pattern_name)
        with open(pattern_path, "wb") as handle:
            handle.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\nstartxref\n0\n%%EOF")
        try:
            resolution = resolve_series_template(series.id, "LETTER", "zz")
            assert resolution.path == pattern_path
            assert resolution.source == "pattern"
            assert "explicit mapping missing; falling back source=pattern" in caplog.text
        finally:
            os.remove(pattern_path)


def test_resolve_series_template_falls_back_to_legacy(app, caplog):
    with app.app_context():
        caplog.set_level("INFO")
        series = CertificateTemplateSeries(code="SER3", name="Series 3")
        db.session.add(series)
        db.session.commit()
        assets_dir = os.path.join(app.root_path, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        legacy_name = "fncert_letter_pt.pdf"
        legacy_path = os.path.join(assets_dir, legacy_name)
        with open(legacy_path, "wb") as handle:
            handle.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\nstartxref\n0\n%%EOF")
        try:
            resolution = resolve_series_template(series.id, "LETTER", "pt")
            assert resolution.path == legacy_path
            assert resolution.source == "legacy"
        finally:
            os.remove(legacy_path)


def test_resolve_series_template_missing_includes_attempts(app):
    with app.app_context():
        series = CertificateTemplateSeries(code="SER4", name="Series 4")
        mapping = CertificateTemplate(
            series=series,
            language="zz",
            size="A4",
            filename="missing_explicit.pdf",
        )
        db.session.add_all([series, mapping])
        db.session.commit()
        with pytest.raises(FileNotFoundError) as exc:
            resolve_series_template(series.id, "A4", "zz")
        message = str(exc.value)
        assert "missing_explicit.pdf" in message
        assert "fncert_template_a4_zz.pdf" in message
        assert "fncert_a4_zz.pdf" in message


def _setup_cert(app):
    with app.app_context():
        series = CertificateTemplateSeries(code="SER", name="Series")
        tmpl = CertificateTemplate(
            series=series,
            language="en",
            size="A4",
            filename="fncert_template_a4_en.pdf",
            badge_filename="foundations.webp",
        )
        wt = WorkshopType(
            code="FOO",
            name="Foo",
            cert_series="SER",
        )
        sess = Session(
            title="S1",
            workshop_type=wt,
            start_date=date(2024, 1, 1),
            number_of_class_days=1,
        )
        acct = ParticipantAccount(email="p@example.com", full_name="P")
        part = Participant(email="p@example.com", full_name="P", account=acct)
        admin = User(email="a@example.com", is_admin=True)
        db.session.add_all([series, tmpl, wt, sess, acct, part, admin])
        db.session.flush()
        link = SessionParticipant(
            session_id=sess.id, participant_id=part.id, completion_date=date(2024, 1, 2)
        )
        db.session.add(link)
        db.session.flush()
        attendance = ParticipantAttendance(
            session_id=sess.id,
            participant_id=part.id,
            day_index=1,
            attended=True,
        )
        db.session.add(attendance)
        db.session.commit()
        render_certificate(sess, acct)
        cert = Certificate.query.filter_by(
            session_id=sess.id, participant_id=part.id
        ).one()
        return sess, part, acct, cert, admin.id


def _build_session(
    app,
    *,
    mark_full_attendance: bool,
    code_suffix: str,
) -> tuple[int, int, int, int]:
    with app.app_context():
        series_code = f"SER{code_suffix}"
        series = CertificateTemplateSeries(code=series_code, name=f"Series {code_suffix}")
        tmpl = CertificateTemplate(
            series=series,
            language="en",
            size="A4",
            filename="fncert_template_a4_en.pdf",
        )
        wt = WorkshopType(code=f"WT{code_suffix}", name="Foo", cert_series=series_code)
        sess = Session(
            title="S",
            workshop_type=wt,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 2),
            number_of_class_days=1,
            delivered=True,
        )
        acct = ParticipantAccount(email=f"{code_suffix.lower()}@example.com", full_name=f"P{code_suffix}")
        part = Participant(
            email=f"{code_suffix.lower()}@example.com",
            full_name=f"P{code_suffix}",
            account=acct,
        )
        admin = User(email=f"admin{code_suffix}@example.com", is_admin=True)
        db.session.add_all([series, tmpl, wt, sess, acct, part, admin])
        db.session.flush()
        link = SessionParticipant(
            session_id=sess.id,
            participant_id=part.id,
            completion_date=date(2024, 2, 2),
        )
        db.session.add(link)
        if mark_full_attendance:
            db.session.add(
                ParticipantAttendance(
                    session_id=sess.id,
                    participant_id=part.id,
                    day_index=1,
                    attended=True,
                )
            )
        db.session.commit()
        return sess.id, part.id, acct.id, admin.id


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
    sess, part, acct, cert, admin_id = _setup_cert(app)
    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = admin_id
    resp = client.get(f"/sessions/{sess.id}")
    html = resp.data.decode()
    assert '<img src="/badges/foundations.webp"' in html
    assert "Badge" in html
    assert f'href="/certificates/{cert.pdf_path}"' in html
    assert "Certificate" in html


def test_badge_hidden_when_missing(app):
    sess, part, acct, cert, admin_id = _setup_cert(app)
    mapping = CertificateTemplate.query.first()
    mapping.badge_filename = None
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = admin_id
    resp = client.get(f"/sessions/{sess.id}")
    html = resp.data.decode()
    assert '<img src="/badges/' not in html


def test_certificate_link_hidden_when_missing(app):
    sess, part, acct, cert, admin_id = _setup_cert(app)
    # remove certificate record to simulate missing certificate
    with app.app_context():
        db.session.delete(cert)
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = admin_id
    resp = client.get(f"/sessions/{sess.id}")
    html = resp.data.decode()
    assert 'href="/certificates/' not in html


def test_render_certificate_requires_full_attendance(app):
    session_id, participant_id, account_id, _ = _build_session(
        app, mark_full_attendance=False, code_suffix="X"
    )
    with app.app_context():
        sess = db.session.get(Session, session_id)
        account = db.session.get(ParticipantAccount, account_id)
        with pytest.raises(CertificateAttendanceError):
            render_certificate(sess, account)
        cert = Certificate.query.filter_by(
            session_id=session_id, participant_id=participant_id
        ).first()
        assert cert is None
        cert_dir = os.path.join(
            "/srv/certificates",
            str((sess.start_date or date.today()).year),
            str(sess.id),
        )
        assert not os.path.exists(cert_dir)


def test_generate_single_blocks_without_full_attendance(app):
    session_id, participant_id, account_id, admin_id = _build_session(
        app, mark_full_attendance=False, code_suffix="Y"
    )
    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = admin_id
    resp = client.post(
        f"/sessions/{session_id}/participants/{participant_id}/generate",
        data={"action": "generate"},
    )
    assert resp.status_code == 400
    assert resp.is_json
    assert resp.get_json()["error"] == "Full attendance required to generate certificate."
    with app.app_context():
        cert = Certificate.query.filter_by(
            session_id=session_id, participant_id=participant_id
        ).first()
        assert cert is None


def test_render_for_session_skips_non_full_attendance(app):
    session_id, participant_id, account_id, _ = _build_session(
        app, mark_full_attendance=False, code_suffix="Z"
    )
    with app.app_context():
        count, skipped, paths = render_for_session(session_id)
        assert count == 0
        assert skipped == 1
        assert paths == []
        cert = Certificate.query.filter_by(
            session_id=session_id, participant_id=participant_id
        ).first()
        assert cert is None

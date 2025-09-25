import io
from datetime import date
from types import SimpleNamespace

import pytest

from app.app import db
from app.models import (
    Certificate,
    Participant,
    ParticipantAccount,
    PreworkTemplate,
    Session,
    SessionParticipant,
    WorkshopType,
)
from app.services.prework_invites import send_prework_invites
from app.shared.certificates import render_certificate


@pytest.fixture
def admin_user(app):
    from app.models import User

    with app.app_context():
        user = User(
            email="admin@example.com",
            first_name="Admin",
            last_name="User",
            full_name="Admin User",
            is_admin=True,
        )
        db.session.add(user)
        db.session.commit()
        yield user


def _create_session(app, title="Session"):
    with app.app_context():
        wt = WorkshopType(name="Test", code="TST", cert_series="GEN")
        db.session.add(wt)
        sess = Session(
            title=title,
            workshop_type=wt,
            workshop_language="en",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            number_of_class_days=0,
        )
        db.session.add(sess)
        db.session.commit()
        return sess.id


def test_importer_accepts_new_and_legacy_formats(client, app, admin_user):
    session_id = _create_session(app)
    with client.session_transaction() as flask_sess:
        flask_sess["user_id"] = admin_user.id

    new_csv = io.BytesIO(
        b"First Name,Last Name,Email,Title\nAlice,Wonder,alice@example.com,Engineer\n"
    )
    response = client.post(
        f"/sessions/{session_id}/participants/import-csv",
        data={"file": (new_csv, "import.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        participant = Participant.query.filter_by(email="alice@example.com").one()
        assert participant.first_name == "Alice"
        assert participant.last_name == "Wonder"
        assert participant.full_name == "Alice Wonder"
        assert participant.account is not None
        account = participant.account
        assert account.full_name == "Alice Wonder"

    legacy_csv = io.BytesIO(
        b"FullName,Email,Title\nMary Ann van Dyke (Learner),mary@example.com,Director\n"
    )
    response = client.post(
        f"/sessions/{session_id}/participants/import-csv",
        data={"file": (legacy_csv, "legacy.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        participant = Participant.query.filter_by(email="mary@example.com").one()
        assert participant.first_name == "Mary Ann van"
        assert participant.last_name == "Dyke"
        assert participant.full_name == "Mary Ann van Dyke (Learner)"
        assert participant.account.full_name == "Mary Ann van Dyke (Learner)"


def test_prework_email_uses_first_name(monkeypatch, app):
    sent_messages = []

    def fake_send(to_email, subject, body, html=None):
        sent_messages.append({"to": to_email, "subject": subject, "body": body})
        return {"ok": True}

    monkeypatch.setattr("app.services.prework_invites.emailer.send", fake_send)

    session_id = _create_session(app)
    with app.app_context():
        sess = db.session.get(Session, session_id)
        participant = Participant(
            email="learner@example.com",
            first_name="Riley",
            last_name="Jordan",
            full_name="Riley Jordan",
        )
        db.session.add(participant)
        db.session.flush()
        link = SessionParticipant(
            session_id=sess.id, participant_id=participant.id, completion_date=sess.end_date
        )
        db.session.add(link)
        template = PreworkTemplate(
            workshop_type_id=sess.workshop_type_id,
            language="en",
            is_active=True,
            info_html="",
        )
        db.session.add(template)
        db.session.commit()

        app.config.setdefault("SERVER_NAME", "testserver.local")
        with app.test_request_context(base_url="https://testserver.local"):
            result = send_prework_invites(sess)
        assert result.sent_count == 1

    assert sent_messages, "Expected a prework email to be sent"
    assert sent_messages[0]["body"].startswith("Hi Riley,")


def test_render_certificate_uses_display_name(monkeypatch, tmp_path, app):
    template_path = tmp_path / "template.pdf"
    from PyPDF2 import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with open(template_path, "wb") as handle:
        writer.write(handle)

    mapping = SimpleNamespace(
        series=SimpleNamespace(
            id=1,
            layout_config={
                "A4": {
                    "name": {"font": "Helvetica", "y_mm": 120},
                    "workshop": {"font": "Helvetica", "y_mm": 90},
                    "date": {"font": "Helvetica", "y_mm": 60},
                    "details": {"enabled": False},
                }
            },
        )
    )

    monkeypatch.setattr(
        "app.shared.certificates.get_template_mapping",
        lambda session: (mapping, "A4"),
    )
    monkeypatch.setattr(
        "app.shared.certificates.resolve_series_template",
        lambda series_id, size, language: SimpleNamespace(path=str(template_path)),
    )

    session_id = _create_session(app, title="Certificate Session")
    app.config["SITE_ROOT"] = str(tmp_path)
    with app.app_context():
        sess = db.session.get(Session, session_id)
        participant = Participant(
            email="cert@example.com",
            first_name="Taylor",
            last_name="Lee",
            full_name="Taylor Lee",
        )
        db.session.add(participant)
        account = ParticipantAccount(
            email="cert@example.com",
            full_name="Taylor Lee",
            certificate_name="Taylor L.",
        )
        db.session.add(account)
        db.session.flush()
        participant.account_id = account.id
        link = SessionParticipant(
            session_id=sess.id,
            participant_id=participant.id,
            completion_date=sess.end_date,
        )
        db.session.add(link)
        db.session.commit()

        path = render_certificate(sess, account)
        assert path
        cert = Certificate.query.filter_by(participant_id=participant.id).one()
        assert cert.certificate_name == "Taylor L."

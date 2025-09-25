from datetime import date

from app.app import db
from app.models import (
    Participant,
    PreworkTemplate,
    Session,
    SessionParticipant,
    Settings,
    User,
    WorkshopType,
)
from app.services.prework_invites import send_prework_invites


def _ensure_settings() -> Settings:
    settings = Settings.get()
    if not settings:
        settings = Settings(
            id=1,
            smtp_host="",
            smtp_port=0,
            smtp_user="",
            smtp_from_default="",
            smtp_from_name="",
            use_tls=True,
            use_ssl=False,
            notify_account_invite_active=True,
            notify_prework_invite_active=True,
            notify_materials_processors_active=True,
            notify_certificate_delivery_active=True,
        )
        settings.mail_notifications = {}
        db.session.add(settings)
    return settings


def test_account_invites_respect_toggle(app, client, monkeypatch, caplog):
    with app.app_context():
        settings = _ensure_settings()
        settings.notify_account_invite_active = True
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("pw")
        workshop_type = WorkshopType(code="WT-INV", name="Invite", cert_series="fn")
        session = Session(
            title="Invite Session",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            workshop_type=workshop_type,
        )
        participant = Participant(email="learner@example.com", full_name="Learner")
        db.session.add_all([admin, workshop_type, session, participant])
        db.session.flush()
        db.session.add(
            SessionParticipant(session_id=session.id, participant_id=participant.id)
        )
        db.session.commit()
        admin_id = admin.id
        session_id = session.id

    calls: list[tuple] = []

    def _fake_send(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True}

    monkeypatch.setattr("app.routes.sessions.emailer.send", _fake_send)

    with client.session_transaction() as sess:
        sess["user_id"] = admin_id

    response = client.post(
        f"/sessions/{session_id}/prework",
        data={"action": "send_accounts"},
    )
    assert response.status_code == 302
    assert len(calls) == 1

    with app.app_context():
        settings = Settings.get()
        settings.notify_account_invite_active = False
        db.session.commit()

    calls.clear()
    caplog.clear()
    with caplog.at_level("INFO"):
        response = client.post(
            f"/sessions/{session_id}/prework",
            data={"action": "send_accounts"},
        )
    assert response.status_code == 302
    assert len(calls) == 0
    assert any(
        "[MAIL-SKIP] account invite disabled" in record.message
        for record in caplog.records
    )

    with app.app_context():
        settings = Settings.get()
        settings.notify_account_invite_active = True
        db.session.commit()


def test_prework_invites_respect_toggle(app, monkeypatch, caplog):
    with app.app_context():
        settings = _ensure_settings()
        settings.notify_prework_invite_active = True
        facilitator = User(email="facilitator@example.com", is_kt_delivery=True)
        facilitator.set_password("pw")
        workshop_type = WorkshopType(code="WT-PRE", name="Prework", cert_series="fn")
        session = Session(
            title="Prework Session",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            workshop_type=workshop_type,
            lead_facilitator=facilitator,
        )
        participant = Participant(email="prework@example.com", full_name="Student")
        template = PreworkTemplate(
            workshop_type=workshop_type,
            language="en",
            is_active=True,
        )
        db.session.add_all([facilitator, workshop_type, session, participant, template])
        db.session.flush()
        db.session.add(
            SessionParticipant(session_id=session.id, participant_id=participant.id)
        )
        db.session.commit()
        session_id = session.id

    calls: list[tuple] = []

    def _fake_send(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True}

    monkeypatch.setattr("app.services.prework_invites.emailer.send", _fake_send)

    with app.app_context():
        with app.test_request_context(base_url="https://cbs.test"):
            with caplog.at_level("INFO"):
                result = send_prework_invites(db.session.get(Session, session_id))
    assert result.sent_count == 1
    assert result.mail_suppressed is False
    assert len(calls) == 1

    with app.app_context():
        settings = Settings.get()
        settings.notify_prework_invite_active = False
        db.session.commit()

    calls.clear()
    caplog.clear()
    with app.app_context():
        with app.test_request_context(base_url="https://cbs.test"):
            with caplog.at_level("INFO"):
                result = send_prework_invites(db.session.get(Session, session_id))
    assert result.sent_count == 0
    assert result.mail_suppressed is True
    assert len(calls) == 0
    assert any(
        "[MAIL-SKIP] prework invite disabled" in record.message
        for record in caplog.records
    )

    with app.app_context():
        settings = Settings.get()
        settings.notify_prework_invite_active = True
        db.session.commit()

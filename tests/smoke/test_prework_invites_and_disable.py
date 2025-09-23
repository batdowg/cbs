from datetime import date

import pytest

from app.app import db
from app.models import (
    Participant,
    PreworkAssignment,
    PreworkTemplate,
    Session,
    SessionParticipant,
    User,
    WorkshopType,
)
from app.services.prework_invites import send_prework_invites


@pytest.fixture(autouse=True)
def _patch_emailer(monkeypatch):
    monkeypatch.setattr("app.emailer.send", lambda *args, **kwargs: {"ok": True})


def test_prework_invites_and_disable_modes(app, client):
    with app.app_context():
        facilitator = User(email="facilitator@example.com", is_kt_delivery=True)
        facilitator.set_password("pw")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        session = Session(
            title="Prework",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            workshop_type=workshop_type,
            lead_facilitator=facilitator,
        )
        participant = Participant(
            email="participant@example.com", full_name="Learner"
        )
        template = PreworkTemplate(
            workshop_type=workshop_type,
            language="en",
            is_active=True,
        )
        db.session.add_all([facilitator, workshop_type, session, participant, template])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=session.id, participant_id=participant.id))
        db.session.commit()
        facilitator_id = facilitator.id
        session_id = session.id
        workshop_type_id = workshop_type.id

    with app.app_context():
        with app.test_request_context():
            result = send_prework_invites(db.session.get(Session, session_id), sender_id=facilitator_id)
        assert result.sent_count == 1
        assignment = PreworkAssignment.query.filter_by(session_id=session_id).one()
        assert assignment.status == "SENT"
        assert assignment.sent_at is not None

    with client.session_transaction() as sess:
        sess["user_id"] = facilitator_id

    notify_resp = client.post(
        f"/workshops/{session_id}/prework/disable",
        data={"mode": "notify"},
        follow_redirects=True,
    )
    notify_html = notify_resp.get_data(as_text=True)
    assert "Prework disabled. Sent 1 account email" in notify_html
    with app.app_context():
        session = db.session.get(Session, session_id)
        assignment = PreworkAssignment.query.filter_by(session_id=session_id).one()
        assert session.prework_disabled is True
        assert session.prework_disable_mode == "notify"
        assert assignment.status == "WAIVED"

    with app.app_context():
        silent_session = Session(
            title="Silent",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            workshop_type=db.session.get(WorkshopType, workshop_type_id),
            lead_facilitator=db.session.get(User, facilitator_id),
        )
        db.session.add(silent_session)
        db.session.commit()
        silent_id = silent_session.id

    silent_resp = client.post(
        f"/workshops/{silent_id}/prework/disable",
        data={"mode": "silent"},
        follow_redirects=True,
    )
    assert "Prework disabled without sending account emails." in silent_resp.get_data(as_text=True)

    delivered_resp = client.post(
        f"/sessions/{silent_id}/mark-delivered",
        follow_redirects=True,
    )
    assert "Session marked delivered" in delivered_resp.get_data(as_text=True)
    with app.app_context():
        silent = db.session.get(Session, silent_id)
        assert silent.prework_disable_mode == "silent"
        assert silent.delivered is True

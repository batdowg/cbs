from datetime import date, time

import pytest

from app import emailer
from app.app import create_app, db
from app.models import (
    Participant,
    ParticipantAccount,
    PreworkAssignment,
    PreworkQuestion,
    PreworkTemplate,
    Session,
    SessionParticipant,
    User,
    WorkshopType,
)


@pytest.fixture
def app_context():
    app = create_app()
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    yield app
    db.session.remove()
    db.drop_all()
    ctx.pop()


def _seed_session(with_completion: bool = True):
    facilitator = User(email="fac@example.com", is_kt_delivery=True)
    facilitator.set_password("pw")
    wt = WorkshopType(code="PWV", name="Prework View", cert_series="fn")
    template = PreworkTemplate(workshop_type=wt, info_html="info")
    question = PreworkQuestion(template=template, position=1, text="Q1", kind="TEXT")
    sess = Session(
        title="Workshop",
        workshop_type=wt,
        start_date=date.today(),
        end_date=date.today(),
        daily_start_time=time(9, 0),
        workshop_language="en",
        lead_facilitator=facilitator,
    )
    sess.facilitators = [facilitator]
    participant = Participant(full_name="Submitted", email="submitted@example.com")
    pending_participant = Participant(full_name="Pending", email="pending@example.com")
    db.session.add_all(
        [
            facilitator,
            wt,
            template,
            question,
            sess,
            participant,
            pending_participant,
        ]
    )
    db.session.flush()
    db.session.add_all(
        [
            SessionParticipant(session=sess, participant=participant),
            SessionParticipant(session=sess, participant=pending_participant),
        ]
    )
    db.session.commit()

    if with_completion:
        account = ParticipantAccount(
            email=participant.email,
            full_name=participant.full_name,
            certificate_name=participant.full_name,
        )
        participant.account = account
        db.session.add(account)
        db.session.flush()
        assignment = PreworkAssignment(
            session=sess,
            participant_account=account,
            template=template,
            status="COMPLETED",
            completed_at=date.today(),
            snapshot_json={"questions": [], "resources": []},
        )
        db.session.add(assignment)
        db.session.commit()

    return sess, facilitator, participant, pending_participant


def test_workshop_view_shows_prework_status(app_context):
    app = app_context
    sess, facilitator, _, pending_participant = _seed_session()
    client = app.test_client()
    with client.session_transaction() as sess_data:
        sess_data["user_id"] = facilitator.id
    resp = client.get(f"/workshops/{sess.id}")
    html = resp.get_data(as_text=True)
    assert "Submitted" in html
    assert "Not submitted" in html
    assert "Send prework" in html
    assert pending_participant.full_name in html


def test_send_prework_endpoint_filters_by_participant(app_context, monkeypatch):
    app = app_context
    sess, facilitator, _, pending_participant = _seed_session(with_completion=False)
    sent_to = []

    def fake_send(to, subject, body, html):
        sent_to.append(to)
        return {"ok": True}

    monkeypatch.setattr(emailer, "send", fake_send)

    client = app.test_client()
    with client.session_transaction() as sess_data:
        sess_data["user_id"] = facilitator.id
    resp = client.post(
        f"/sessions/{sess.id}/prework/send",
        data={"participant_ids[]": str(pending_participant.id)},
    )
    assert resp.status_code == 302
    assert sent_to == [pending_participant.email]
    assignment = PreworkAssignment.query.filter_by(session_id=sess.id).first()
    assert assignment is not None
    assert assignment.sent_at is not None


def test_send_prework_blocks_unauthorized(app_context):
    app = app_context
    sess, facilitator, _, _ = _seed_session(with_completion=False)
    other_user = User(email="other@example.com")
    db.session.add(other_user)
    db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess_data:
        sess_data["user_id"] = other_user.id
    resp = client.post(f"/sessions/{sess.id}/prework/send")
    assert resp.status_code == 403


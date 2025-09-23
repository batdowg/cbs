import os
from datetime import date, time

import pytest

from app.app import create_app, db
from app.models import (
    WorkshopType,
    PreworkTemplate,
    PreworkQuestion,
    Session,
    ParticipantAccount,
    Participant,
    SessionParticipant,
    PreworkAssignment,
    User,
    SessionFacilitator,
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


def _setup(app, *, prework_disabled: bool = False):
    with app.app_context():
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        db.session.add(wt)
        db.session.flush()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q1", kind="TEXT"))
        acct = ParticipantAccount(email="csa@example.com", full_name="CSA", is_active=True)
        part = Participant(email="csa@example.com", full_name="CSA", account=acct)
        facilitator = User(
            email="fac@example.com",
            full_name="Facilitator One",
            is_kt_delivery=True,
            phone="+1 555 0100",
        )
        sess = Session(
            title="S",
            workshop_type=wt,
            start_date=date(2024, 1, 5),
            end_date=date(2024, 1, 7),
            daily_start_time=time(9, 0),
            daily_end_time=time(17, 0),
            timezone="UTC",
            location="Austin, TX",
            prework_disabled=prework_disabled,
        )
        db.session.add_all([acct, part, sess, facilitator])
        db.session.flush()
        sess.lead_facilitator_id = facilitator.id
        db.session.add(SessionFacilitator(session_id=sess.id, user_id=facilitator.id))
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        assign = PreworkAssignment(
            session_id=sess.id,
            participant_account_id=acct.id,
            template_id=tpl.id,
            status="SENT",
            snapshot_json={"questions": [], "resources": []},
        )
        other_acct = ParticipantAccount(email="other@example.com", full_name="Other", is_active=True)
        db.session.add_all([assign, other_acct])
        db.session.commit()
        return {
            "account_id": acct.id,
            "assignment_id": assign.id,
            "session_id": sess.id,
            "facilitator_email": facilitator.email,
            "other_account_id": other_acct.id,
        }


def _login(client, account_id):
    with client.session_transaction() as sess:
        sess["participant_account_id"] = account_id


def test_my_workshops_card_shows_details(app):
    data = _setup(app)
    client = app.test_client()
    _login(client, data["account_id"])
    resp = client.get("/my-workshops")
    assert f"/prework/{data['assignment_id']}".encode() in resp.data
    assert b"Complete prework" in resp.data
    assert b"Facilitator One" in resp.data
    assert data["facilitator_email"].encode() in resp.data
    assert b"Austin" in resp.data
    assert b"5 Jan 2024" in resp.data
    assert b"09:00" in resp.data


def test_my_workshops_no_prework_when_disabled(app):
    data = _setup(app, prework_disabled=True)
    client = app.test_client()
    _login(client, data["account_id"])
    resp = client.get("/my-workshops")
    assert b"No prework" in resp.data


def test_facilitator_info_hidden_from_unassigned(app):
    data = _setup(app)
    client = app.test_client()
    _login(client, data["other_account_id"])
    resp = client.get("/my-workshops")
    assert data["facilitator_email"].encode() not in resp.data

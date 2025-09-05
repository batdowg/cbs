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


def _setup(app):
    with app.app_context():
        wt = WorkshopType(code="WT", short_code="WT", name="WT")
        db.session.add(wt)
        db.session.flush()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q1", kind="TEXT"))
        acct = ParticipantAccount(email="csa@example.com", full_name="CSA", is_active=True)
        part = Participant(email="csa@example.com", full_name="CSA", account=acct)
        sess = Session(
            title="S",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            daily_start_time=time(9, 0),
            timezone="UTC",
        )
        db.session.add_all([acct, part, sess])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        assign = PreworkAssignment(
            session_id=sess.id,
            participant_account_id=acct.id,
            template_id=tpl.id,
            status="SENT",
            snapshot_json={"questions": [], "resources": []},
        )
        db.session.add(assign)
        db.session.commit()
        return acct.id, assign.id


def _login(client, account_id):
    with client.session_transaction() as sess:
        sess["participant_account_id"] = account_id


def test_my_workshops_prework_action(app):
    account_id, assign_id = _setup(app)
    client = app.test_client()
    _login(client, account_id)
    resp = client.get("/my-workshops")
    assert f"/prework/{assign_id}".encode() in resp.data
    resp2 = client.get(f"/prework/{assign_id}")
    assert resp2.status_code == 200

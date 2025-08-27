from datetime import date, time

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
    PreworkAnswer,
)


def test_assignment_completion():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="PW", name="Prework")
        db.session.add(wt)
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q1"))
        db.session.commit()
        sess = Session(title="S1", workshop_type_id=wt.id, start_date=date.today(), daily_start_time=time(8, 0))
        acct = ParticipantAccount(email="a@example.com", full_name="A")
        part = Participant(email="a@example.com", full_name="A", account=acct)
        db.session.add_all([sess, acct, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        snapshot = {"questions": [{"index": 1, "text": "Q1", "required": True}], "resources": []}
        assign = PreworkAssignment(
            session_id=sess.id,
            participant_account_id=acct.id,
            template_id=tpl.id,
            status="SENT",
            snapshot_json=snapshot,
        )
        db.session.add(assign)
        db.session.commit()
        db.session.add(
            PreworkAnswer(
                assignment_id=assign.id, question_index=1, answer_text="A1"
            )
        )
        db.session.commit()
        assign.update_completion()
        db.session.commit()
        assert assign.status == "COMPLETED"


def test_nav_gating_prework():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="PW2", name="Prework2")
        db.session.add(wt)
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q1"))
        db.session.commit()
        future = date.fromordinal(date.today().toordinal() + 5)
        sess = Session(title="Fut", workshop_type_id=wt.id, start_date=future, daily_start_time=time(8, 0))
        acct = ParticipantAccount(email="b@example.com", full_name="B")
        part = Participant(email="b@example.com", full_name="B", account=acct)
        db.session.add_all([sess, acct, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        snapshot = {"questions": [{"index": 1, "text": "Q1", "required": True}], "resources": []}
        assign = PreworkAssignment(
            session_id=sess.id,
            participant_account_id=acct.id,
            template_id=tpl.id,
            status="SENT",
            snapshot_json=snapshot,
        )
        db.session.add(assign)
        db.session.commit()
        account_id = acct.id
    with app.test_client() as c:
        with c.session_transaction() as sess_data:
            sess_data["participant_account_id"] = account_id
        resp = c.get("/home", follow_redirects=True)
        assert b"My Prework" in resp.data
        assert b"My Resources" not in resp.data

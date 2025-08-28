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
from sqlalchemy.exc import IntegrityError
import pytest


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
        db.session.add(
            PreworkQuestion(template_id=tpl.id, position=1, text="Q1", kind="TEXT")
        )
        db.session.commit()
        sess = Session(title="S1", workshop_type_id=wt.id, start_date=date.today(), daily_start_time=time(8, 0))
        acct = ParticipantAccount(email="a@example.com", full_name="A")
        part = Participant(email="a@example.com", full_name="A", account=acct)
        db.session.add_all([sess, acct, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        snapshot = {
            "questions": [
                {
                    "index": 1,
                    "text": "Q1",
                    "required": True,
                    "kind": "TEXT",
                }
            ],
            "resources": [],
        }
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
        db.session.add(
            PreworkQuestion(template_id=tpl.id, position=1, text="Q1", kind="TEXT")
        )
        db.session.commit()
        future = date.fromordinal(date.today().toordinal() + 5)
        sess = Session(title="Fut", workshop_type_id=wt.id, start_date=future, daily_start_time=time(8, 0))
        acct = ParticipantAccount(email="b@example.com", full_name="B")
        part = Participant(email="b@example.com", full_name="B", account=acct)
        db.session.add_all([sess, acct, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        snapshot = {
            "questions": [
                {
                    "index": 1,
                    "text": "Q1",
                    "required": True,
                    "kind": "TEXT",
                }
            ],
            "resources": [],
        }
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


def test_item_index_unique():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="MI", name="ItemIdx")
        db.session.add(wt)
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(
            PreworkQuestion(template_id=tpl.id, position=1, text="Q1", kind="TEXT")
        )
        db.session.commit()
        sess = Session(title="S1", workshop_type_id=wt.id)
        acct = ParticipantAccount(email="c@example.com", full_name="C")
        part = Participant(email="c@example.com", full_name="C", account=acct)
        db.session.add_all([sess, acct, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        snapshot = {
            "questions": [
                {"index": 1, "text": "Q1", "required": True, "kind": "TEXT"}
            ],
            "resources": [],
        }
        assign = PreworkAssignment(
            session_id=sess.id,
            participant_account_id=acct.id,
            template_id=tpl.id,
            status="SENT",
            snapshot_json=snapshot,
        )
        db.session.add(assign)
        db.session.commit()
        ans1 = PreworkAnswer(
            assignment_id=assign.id, question_index=1, answer_text="A"
        )
        db.session.add(ans1)
        db.session.commit()
        assert ans1.item_index == 0
        db.session.add(
            PreworkAnswer(
                assignment_id=assign.id,
                question_index=1,
                item_index=0,
                answer_text="B",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_list_question_autosave_and_completion():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="LQ", name="ListQ")
        db.session.add(wt)
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(
            PreworkQuestion(
                template_id=tpl.id,
                position=1,
                text="ListQ",
                kind="LIST",
                min_items=2,
                max_items=3,
            )
        )
        db.session.commit()
        sess = Session(title="S1", workshop_type_id=wt.id)
        acct = ParticipantAccount(email="d@example.com", full_name="D")
        part = Participant(email="d@example.com", full_name="D", account=acct)
        db.session.add_all([sess, acct, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        snapshot = {
            "questions": [
                {
                    "index": 1,
                    "text": "ListQ",
                    "required": True,
                    "kind": "LIST",
                    "min_items": 2,
                    "max_items": 3,
                }
            ],
            "resources": [],
        }
        assign = PreworkAssignment(
            session_id=sess.id,
            participant_account_id=acct.id,
            template_id=tpl.id,
            status="SENT",
            snapshot_json=snapshot,
        )
        db.session.add(assign)
        db.session.commit()
        assign_id = assign.id
        account_id = acct.id
    with app.test_client() as c:
        with c.session_transaction() as sess_data:
            sess_data["participant_account_id"] = account_id
        resp = c.get(f"/prework/{assign_id}")
        assert b"Add another" in resp.data
        c.post(
            f"/prework/{assign_id}/autosave",
            json={"question_index": 1, "item_index": 0, "text": "A"},
        )
        c.post(
            f"/prework/{assign_id}/autosave",
            json={"question_index": 1, "item_index": 1, "text": "B"},
        )
    with app.app_context():
        assign = db.session.get(PreworkAssignment, assign_id)
        assign.update_completion()
        db.session.commit()
        assert assign.status == "COMPLETED"


def test_prework_download_route():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="DL", name="Download")
        db.session.add(wt)
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(
            PreworkQuestion(template_id=tpl.id, position=1, text="Q1", kind="TEXT")
        )
        db.session.commit()
        sess = Session(title="S1", workshop_type_id=wt.id)
        acct = ParticipantAccount(email="e@example.com", full_name="E")
        part = Participant(email="e@example.com", full_name="E", account=acct)
        db.session.add_all([sess, acct, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        snapshot = {
            "questions": [
                {"index": 1, "text": "Q1", "required": True, "kind": "TEXT"}
            ],
            "resources": [],
        }
        assign = PreworkAssignment(
            session_id=sess.id,
            participant_account_id=acct.id,
            template_id=tpl.id,
            status="SENT",
            snapshot_json=snapshot,
        )
        db.session.add(assign)
        db.session.commit()
        assign_id = assign.id
        account_id = acct.id
    with app.test_client() as c:
        with c.session_transaction() as sess_data:
            sess_data["participant_account_id"] = account_id
        resp = c.get(f"/prework/{assign_id}/download")
        assert resp.status_code == 200
        assert b"window.print" in resp.data

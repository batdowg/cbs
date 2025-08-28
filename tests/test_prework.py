from datetime import date, time
import secrets

from app.app import create_app, db
from app import emailer
from app.models import (
    User,
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


def test_no_prework_toggle_disables_send_prework(monkeypatch):
    app = create_app()
    with app.app_context():
        db.create_all()
        user = User(email="admin@example.com", is_app_admin=True)
        wt = WorkshopType(code="NP", name="NoPrework")
        db.session.add_all([user, wt])
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q", kind="TEXT"))
        sess = Session(title="S", workshop_type_id=wt.id, start_date=date.today(), daily_start_time=time(8, 0))
        part = Participant(email="p@example.com", full_name="P")
        db.session.add_all([sess, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        db.session.commit()
        sess_id = sess.id
        user_id = user.id
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = user_id
        c.post(f"/sessions/{sess_id}/prework", data={"action": "toggle_no_prework", "no_prework": "1"})
        c.post(f"/sessions/{sess_id}/prework", data={"action": "send_all"})
        with app.app_context():
            assert Session.query.get(sess_id).no_prework is True
            assert PreworkAssignment.query.count() == 0


def test_account_invite_sets_timestamp(monkeypatch):
    app = create_app()
    with app.app_context():
        db.create_all()
        user = User(email="admin2@example.com", is_app_admin=True)
        wt = WorkshopType(code="AI", name="AcctInvite")
        db.session.add_all([user, wt])
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q", kind="TEXT"))
        sess = Session(title="S2", workshop_type_id=wt.id, start_date=date.today(), daily_start_time=time(8, 0))
        part = Participant(email="p2@example.com", full_name="P2")
        db.session.add_all([sess, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        db.session.commit()
        sess_id = sess.id
        user_id = user.id
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = user_id
        token = "fixedtoken"
        monkeypatch.setattr(emailer, "send", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(secrets, "token_urlsafe", lambda n: token)
        c.post(f"/sessions/{sess_id}/prework", data={"action": "send_accounts"})
        with app.app_context():
            assignment = PreworkAssignment.query.filter_by(session_id=sess_id).first()
            account = ParticipantAccount.query.filter_by(email="p2@example.com").first()
            assert assignment and assignment.account_sent_at is not None
            assert account and account.login_magic_hash is not None
            account_id = account.id
        resp = c.get(f"/account/a/{account_id}/{token}")
        assert resp.status_code == 302
        with c.session_transaction() as s:
            assert s.get("participant_account_id") == account_id


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

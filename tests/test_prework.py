from datetime import date, time
import secrets

from app.app import create_app, db
from app import emailer
from app.shared.constants import DEFAULT_PARTICIPANT_PASSWORD
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


pytestmark = pytest.mark.smoke


def test_assignment_completion():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="PW", name="Prework", cert_series="fn")
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


def test_prework_template_unique_per_language():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="PWL", name="Prework Lang", cert_series="fn")
        db.session.add(wt)
        db.session.flush()
        tpl_en = PreworkTemplate(workshop_type=wt, language="en")
        tpl_es = PreworkTemplate(workshop_type=wt, language="es")
        db.session.add_all([tpl_en, tpl_es])
        db.session.commit()

        db.session.add(PreworkTemplate(workshop_type=wt, language="en"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

def test_no_prework_toggle_disables_send_prework(monkeypatch):
    app = create_app()
    with app.app_context():
        db.create_all()
        user = User(email="admin@example.com", is_app_admin=True)
        wt = WorkshopType(code="NP", name="NoPrework", cert_series="fn")
        db.session.add_all([user, wt])
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q", kind="TEXT"))
        sess = Session(
            title="S",
            workshop_type_id=wt.id,
            start_date=date.today(),
            daily_start_time=time(8, 0),
        )
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
            sess = Session.query.get(sess_id)
            assert sess.no_prework is True
            assert sess.prework_disabled is True
            assert sess.prework_disable_mode is None
            assert PreworkAssignment.query.count() == 0


def test_account_invite_sets_timestamp(monkeypatch):
    app = create_app()
    with app.app_context():
        db.create_all()
        user = User(email="admin2@example.com", is_app_admin=True)
        wt = WorkshopType(code="AI", name="AcctInvite", cert_series="fn")
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
        sent = {}

        def fake_send(to, subject, body, html):
            sent["body"] = body
            return {"ok": True}

        monkeypatch.setattr(emailer, "send", fake_send)
        monkeypatch.setattr(secrets, "token_urlsafe", lambda n: token)
        c.post(f"/sessions/{sess_id}/prework", data={"action": "send_accounts"})
        with app.app_context():
            assignment = PreworkAssignment.query.filter_by(session_id=sess_id).first()
            account = ParticipantAccount.query.filter_by(email="p2@example.com").first()
            assert assignment and assignment.account_sent_at is not None
            assert account and account.login_magic_hash is not None
            account_id = account.id
        assert DEFAULT_PARTICIPANT_PASSWORD in sent["body"]
        resp = c.get(f"/account/a/{account_id}/{token}")
        assert resp.status_code == 302
        with c.session_transaction() as s:
            assert s.get("participant_account_id") == account_id


def test_nav_gating_prework():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="PW2", name="Prework2", cert_series="fn")
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
        resp = c.get("/my-workshops")
        assert b"Prework" in resp.data


def test_learner_prework_session_language_flow():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(
            code="LANG",
            name="Language",
            cert_series="fn",
            supported_languages=["en", "es"],
        )
        tpl_en = PreworkTemplate(workshop_type=wt, language="en")
        tpl_es = PreworkTemplate(workshop_type=wt, language="es")
        q_en = PreworkQuestion(template=tpl_en, position=1, text="English Q", kind="TEXT")
        q_es = PreworkQuestion(template=tpl_es, position=1, text="Spanish Q", kind="TEXT")
        session = Session(
            title="Idioma",
            workshop_type=wt,
            start_date=date.today(),
            daily_start_time=time(9, 0),
            workshop_language="es",
        )
        account = ParticipantAccount(email="learner@example.com", full_name="Learner")
        participant = Participant(
            email="learner@example.com", full_name="Learner", account=account
        )
        db.session.add_all(
            [wt, tpl_en, tpl_es, q_en, q_es, session, account, participant]
        )
        db.session.flush()
        db.session.add(
            SessionParticipant(session_id=session.id, participant_id=participant.id)
        )
        snapshot = {
            "questions": [
                {
                    "index": 1,
                    "text": "Spanish Q",
                    "required": True,
                    "kind": "TEXT",
                }
            ],
            "resources": [],
        }
        assignment = PreworkAssignment(
            session_id=session.id,
            participant_account_id=account.id,
            template=tpl_es,
            status="SENT",
            snapshot_json=snapshot,
        )
        db.session.add(assignment)
        db.session.commit()
        assignment_id = assignment.id
        account_id = account.id

    with app.test_client() as client:
        with client.session_transaction() as sess_data:
            sess_data["participant_account_id"] = account_id

        resp = client.get(f"/prework/{assignment_id}")
        assert resp.status_code == 200
        assert b"Spanish Q" in resp.data

        resp_post = client.post(
            f"/prework/{assignment_id}",
            data={"q1": "respuesta"},
            follow_redirects=True,
        )
        assert resp_post.status_code == 200

    with app.app_context():
        answer = PreworkAnswer.query.filter_by(
            assignment_id=assignment_id, question_index=1
        ).first()
        assert answer is not None
        assert answer.answer_text == "respuesta"


def test_item_index_unique():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="MI", name="ItemIdx", cert_series="fn")
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
        wt = WorkshopType(code="LQ", name="ListQ", cert_series="fn")
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


def test_prework_form_saves_all_list_entries():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="FORM", name="Form Save", cert_series="fn")
        db.session.add(wt)
        db.session.flush()
        template = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(template)
        db.session.flush()
        db.session.add(
            PreworkQuestion(
                template_id=template.id,
                position=1,
                text="<p>List prompt</p>",
                kind="LIST",
                min_items=1,
                max_items=5,
            )
        )
        session = Session(title="Save", workshop_type_id=wt.id)
        account = ParticipantAccount(email="save@example.com", full_name="Saver")
        db.session.add_all([session, account])
        db.session.flush()
        snapshot = {
            "questions": [
                {
                    "index": 1,
                    "text": "<p>List prompt</p>",
                    "required": True,
                    "kind": "LIST",
                    "min_items": 1,
                    "max_items": 5,
                }
            ],
            "resources": [],
        }
        assignment = PreworkAssignment(
            session_id=session.id,
            participant_account_id=account.id,
            template_id=template.id,
            status="SENT",
            snapshot_json=snapshot,
        )
        db.session.add(assignment)
        db.session.commit()
        assign_id = assignment.id
        account_id = account.id
    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["participant_account_id"] = account_id
        resp = client.post(
            f"/prework/{assign_id}",
            data={
                "answers[1][]": [
                    " First response ",
                    "Second response",
                    "Third response",
                ]
            },
        )
        assert resp.status_code == 302
    with app.app_context():
        answers = (
            PreworkAnswer.query.filter_by(assignment_id=assign_id)
            .order_by(PreworkAnswer.item_index)
            .all()
        )
        assert [a.answer_text for a in answers] == [
            "First response",
            "Second response",
            "Third response",
        ]
        assert [a.item_index for a in answers] == [0, 1, 2]


def test_prework_download_route():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="DL", name="Download", cert_series="fn")
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


def test_staff_send_flows_run(monkeypatch):
    app = create_app()
    with app.app_context():
        db.create_all()
        user = User(email="staff@example.com", is_app_admin=True)
        wt = WorkshopType(code="SF", name="SendFlow", cert_series="fn")
        db.session.add_all([user, wt])
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q", kind="TEXT"))
        sess = Session(
            title="S",
            workshop_type_id=wt.id,
            start_date=date.today(),
            daily_start_time=time(8, 0),
            lead_facilitator_id=user.id,
        )
        part = Participant(email="sf@example.com", full_name="SF")
        db.session.add_all([sess, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        db.session.commit()
        sess_id = sess.id
        user_id = user.id
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = user_id
        monkeypatch.setattr(emailer, "send", lambda *a, **k: {"ok": True})
        c.post(f"/sessions/{sess_id}/prework", data={"action": "send_all"})
        c.post(f"/sessions/{sess_id}/prework", data={"action": "send_accounts"})
    with app.app_context():
        assert ParticipantAccount.query.count() == 1
        assert PreworkAssignment.query.count() == 1


def test_contractor_can_send_prework(monkeypatch):
    app = create_app()
    with app.app_context():
        db.create_all()
        user = User(email="cont@example.com", is_kt_contractor=True)
        wt = WorkshopType(code="CT", name="Contractor", cert_series="fn")
        db.session.add_all([user, wt])
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q", kind="TEXT"))
        sess = Session(
            title="S",
            workshop_type_id=wt.id,
            start_date=date.today(),
            daily_start_time=time(8, 0),
            lead_facilitator_id=user.id,
        )
        part = Participant(email="ct@example.com", full_name="CT")
        db.session.add_all([sess, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        db.session.commit()
        sess_id = sess.id
        user_id = user.id
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = user_id
        monkeypatch.setattr(emailer, "send", lambda *a, **k: {"ok": True})
        c.post(f"/sessions/{sess_id}/prework", data={"action": "send_all"})
    with app.app_context():
        assert ParticipantAccount.query.count() == 1
        assert PreworkAssignment.query.count() == 1


def test_contractor_unassigned_forbidden():
    app = create_app()
    with app.app_context():
        db.create_all()
        user = User(email="cont2@example.com", is_kt_contractor=True)
        wt = WorkshopType(code="CT2", name="Contractor2", cert_series="fn")
        db.session.add_all([user, wt])
        db.session.commit()
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q", kind="TEXT"))
        sess = Session(
            title="S2",
            workshop_type_id=wt.id,
            start_date=date.today(),
            daily_start_time=time(8, 0),
        )
        db.session.add(sess)
        db.session.commit()
        sess_id = sess.id
        user_id = user.id
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = user_id
        resp = c.get(f"/sessions/{sess_id}/prework")
        assert resp.status_code == 403


def test_admin_access_with_participant_account():
    app = create_app()
    with app.app_context():
        db.create_all()
        admin = User(email="admin3@example.com", is_app_admin=True)
        wt = WorkshopType(code="AD", name="Admin", cert_series="fn")
        csa = ParticipantAccount(email="csa@example.com", full_name="CSA")
        tpl = PreworkTemplate(workshop_type_id=wt.id, info_html="info")
        db.session.add_all([admin, wt, csa, tpl])
        db.session.flush()
        db.session.add(PreworkQuestion(template_id=tpl.id, position=1, text="Q", kind="TEXT"))
        sess = Session(
            title="S3",
            workshop_type_id=wt.id,
            start_date=date.today(),
            daily_start_time=time(8, 0),
            csa_account_id=csa.id,
        )
        part = Participant(email="p@example.com", full_name="P")
        db.session.add_all([sess, part])
        db.session.flush()
        db.session.add(SessionParticipant(session_id=sess.id, participant_id=part.id))
        db.session.commit()
        sess_id = sess.id
        admin_id = admin.id
        csa_id = csa.id
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = admin_id
            s["participant_account_id"] = csa_id
        resp = c.get(f"/sessions/{sess_id}/prework")
        assert resp.status_code == 200


def test_session_prework_defaults():
    app = create_app()
    with app.app_context():
        db.create_all()
        sess = Session(title="Defaults")
        db.session.add(sess)
        db.session.commit()
        assert sess.prework_disabled is False
        assert sess.prework_disable_mode is None


def test_disable_prework_notify_creates_accounts(monkeypatch):
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="NPW", name="NoPrework", cert_series="fn")
        trainer = User(email="trainer@example.com", is_kt_delivery=True)
        session = Session(
            title="No Prework",
            workshop_type=wt,
            start_date=date.today(),
            daily_start_time=time(8, 0),
            lead_facilitator=trainer,
        )
        participant_with_account = Participant(
            email="hasacct@example.com", full_name="Has Account"
        )
        account = ParticipantAccount(
            email="hasacct@example.com", full_name="Has Account"
        )
        participant_with_account.account = account
        participant_without_account = Participant(
            email="newacct@example.com", full_name="New Account"
        )
        db.session.add_all(
            [
                wt,
                trainer,
                session,
                participant_with_account,
                participant_without_account,
            ]
        )
        db.session.flush()
        db.session.add(
            SessionParticipant(
                session_id=session.id, participant_id=participant_with_account.id
            )
        )
        db.session.add(
            SessionParticipant(
                session_id=session.id,
                participant_id=participant_without_account.id,
            )
        )
        db.session.add(
            PreworkAssignment(
                session_id=session.id,
                participant_account_id=account.id,
                status="PENDING",
            )
        )
        db.session.commit()
        sess_id = session.id
        trainer_id = trainer.id

    sent: list[tuple[str, str]] = []

    def fake_send(to, subject, body, html):
        sent.append((to, subject))
        return {"ok": True}

    monkeypatch.setattr(emailer, "send", fake_send)
    monkeypatch.setattr(secrets, "token_urlsafe", lambda _: "tok")

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = trainer_id
        resp = c.post(
            f"/workshops/{sess_id}/prework/disable",
            data={"mode": "notify"},
        )
        assert resp.status_code == 302

    with app.app_context():
        session = Session.query.get(sess_id)
        assert session.prework_disabled is True
        assert session.prework_disable_mode == "notify"
        assert session.no_prework is True
        assignment = PreworkAssignment.query.filter_by(session_id=sess_id).one()
        assert assignment.status == "WAIVED"
        account = ParticipantAccount.query.filter_by(
            email="hasacct@example.com"
        ).one()
        assert account.login_magic_hash is not None
        new_account = ParticipantAccount.query.filter_by(
            email="newacct@example.com"
        ).one()
        assert new_account.password_hash is not None
        user_one = User.query.filter_by(email="hasacct@example.com").one()
        assert user_one.check_password(DEFAULT_PARTICIPANT_PASSWORD)
        user_two = User.query.filter_by(email="newacct@example.com").one()
        assert user_two.check_password(DEFAULT_PARTICIPANT_PASSWORD)
        assert len(sent) == 2


def test_disable_prework_silent_allows_delivered():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="NPDS", name="NoPreworkDeliver", cert_series="fn")
        admin = User(email="admin@example.com", is_admin=True)
        session = Session(
            title="Deliver",
            workshop_type=wt,
            start_date=date.today(),
            daily_start_time=time(8, 0),
            lead_facilitator=admin,
        )
        db.session.add_all([wt, admin, session])
        db.session.commit()
        sess_id = session.id
        admin_id = admin.id

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = admin_id
        resp = c.post(f"/sessions/{sess_id}/mark-delivered")
        assert resp.status_code == 302

    with app.app_context():
        assert Session.query.get(sess_id).delivered is False

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = admin_id
        resp = c.post(
            f"/workshops/{sess_id}/prework/disable",
            data={"mode": "silent"},
        )
        assert resp.status_code == 302

    with app.app_context():
        session = Session.query.get(sess_id)
        assert session.prework_disabled is True
        assert session.prework_disable_mode == "silent"

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = admin_id
        resp = c.post(f"/sessions/{sess_id}/mark-delivered")
        assert resp.status_code == 302

    with app.app_context():
        session = Session.query.get(sess_id)
        assert session.delivered is True
        assert session.ready_for_delivery is True


def test_workshop_view_shows_none_for_workshop():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="NPWV", name="NoPreworkView", cert_series="fn")
        trainer = User(email="view@example.com", is_kt_delivery=True)
        session = Session(
            title="View",
            workshop_type=wt,
            start_date=date.today(),
            daily_start_time=time(8, 0),
            lead_facilitator=trainer,
        )
        participant = Participant(email="viewp@example.com", full_name="View P")
        db.session.add_all([wt, trainer, session, participant])
        db.session.flush()
        db.session.add(
            SessionParticipant(session_id=session.id, participant_id=participant.id)
        )
        db.session.commit()
        sess_id = session.id
        trainer_id = trainer.id

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = trainer_id
        c.post(f"/workshops/{sess_id}/prework/disable", data={"mode": "silent"})
        resp = c.get(f"/workshops/{sess_id}")
        html = resp.get_data(as_text=True)
    assert "None for workshop" in html
    assert "Send prework to all not submitted" not in html
    assert "No prework – Create accounts" not in html


def test_prework_question_rich_text_rendering():
    app = create_app()
    with app.app_context():
        db.create_all()
        wt = WorkshopType(code="PWR", name="Prework Rich", cert_series="fn")
        tpl = PreworkTemplate(workshop_type=wt, info_html="info")
        raw_text = (
            "<p><strong>Bold</strong> <script>alert(1)</script>"
            "<a href='https://example.com' target='_self' style='color:red'>Link</a></p>"
        )
        db.session.add(
            PreworkQuestion(
                template=tpl,
                position=1,
                text=raw_text,
                kind="TEXT",
            )
        )
        session = Session(
            title="Rich",
            workshop_type=wt,
            start_date=date.today(),
            daily_start_time=time(8, 0),
        )
        account = ParticipantAccount(email="rich@example.com", full_name="Rich")
        participant = Participant(email="rich@example.com", full_name="Rich", account=account)
        db.session.add_all([wt, tpl, session, account, participant])
        db.session.flush()
        db.session.add(
            SessionParticipant(session_id=session.id, participant_id=participant.id)
        )
        assignment = PreworkAssignment(
            session_id=session.id,
            participant_account_id=account.id,
            template_id=tpl.id,
            status="SENT",
            snapshot_json={
                "questions": [
                    {
                        "index": 1,
                        "text": raw_text,
                        "required": True,
                        "kind": "TEXT",
                        "min_items": None,
                        "max_items": None,
                    }
                ],
                "resources": [],
            },
        )
        db.session.add(assignment)
        db.session.commit()
        assignment_id = assignment.id
        account_id = account.id

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["participant_account_id"] = account_id
        resp = c.get(f"/prework/{assignment_id}")
        html = resp.get_data(as_text=True)

    assert "<script>alert" not in html
    assert 'target="_blank" rel="noopener" href="https://example.com"' in html
    assert "<strong>Bold</strong>" in html
    assert "target='_self'" not in html

    import re

    match = re.search(
        r'<div class="question-text rich-text"[^>]*>(.*?)</div>',
        html,
        re.DOTALL,
    )
    assert match is not None
    sanitized = match.group(1)
    assert "style=" not in sanitized

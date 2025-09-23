from datetime import date, datetime, time

import pytest

from app import emailer
from app.app import create_app, db
from app.models import (
    Participant,
    ParticipantAccount,
    PreworkAssignment,
    PreworkQuestion,
    PreworkInvite,
    PreworkTemplate,
    Session,
    SessionParticipant,
    User,
    WorkshopType,
)


pytestmark = pytest.mark.smoke


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
            SessionParticipant(
                session_id=sess.id, participant_id=participant.id
            ),
            SessionParticipant(
                session_id=sess.id, participant_id=pending_participant.id
            ),
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


def test_prework_editor_language_switching(app_context):
    app = app_context
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True)
        wt = WorkshopType(
            code="PWL", name="Prework Lang", cert_series="fn", supported_languages=["en", "es"]
        )
        tpl_en = PreworkTemplate(workshop_type=wt, language="en")
        tpl_es = PreworkTemplate(workshop_type=wt, language="es")
        q_en = PreworkQuestion(template=tpl_en, position=1, text="English question", kind="TEXT")
        q_es = PreworkQuestion(template=tpl_es, position=1, text="Spanish question", kind="TEXT")
        db.session.add_all([admin, wt, tpl_en, tpl_es, q_en, q_es])
        db.session.commit()
        type_id = wt.id
        admin_id = admin.id

    client = app.test_client()
    with client.session_transaction() as sess_data:
        sess_data["user_id"] = admin_id

    resp = client.get(f"/workshop-types/{type_id}/prework")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Language" in html
    assert "English question" in html
    assert "Spanish question" not in html
    assert '<option value="en"' in html
    assert '<option value="es"' in html
    assert 'value="fr"' not in html

    resp_es = client.get(f"/workshop-types/{type_id}/prework?lang=es")
    assert resp_es.status_code == 200
    html_es = resp_es.get_data(as_text=True)
    assert "Spanish question" in html_es
    assert "English question" not in html_es


def test_prework_copy_from_other_workshop(app_context):
    app = app_context
    with app.app_context():
        admin = User(email="admin2@example.com", is_app_admin=True)
        admin.set_password("pw")
        source_type = WorkshopType(
            code="SRC", name="Source", cert_series="fn", supported_languages=["en", "es"]
        )
        dest_type = WorkshopType(
            code="DST", name="Destination", cert_series="fn", supported_languages=["en"]
        )
        source_tpl = PreworkTemplate(
            workshop_type=source_type, language="en", info_html="source info"
        )
        PreworkQuestion(
            template=source_tpl,
            position=1,
            text="Source question",
            kind="LIST",
            min_items=2,
            max_items=4,
        )
        dest_tpl = PreworkTemplate(
            workshop_type=dest_type, language="en", info_html="old info"
        )
        PreworkQuestion(
            template=dest_tpl,
            position=1,
            text="Old question",
            kind="TEXT",
        )
        db.session.add_all([admin, source_type, dest_type, source_tpl, dest_tpl])
        db.session.commit()
        dest_id = dest_type.id
        source_id = source_type.id
        admin_id = admin.id

    client = app.test_client()
    with client.session_transaction() as sess_data:
        sess_data["user_id"] = admin_id

    resp = client.post(
        f"/workshop-types/{dest_id}/prework",
        data={
            "language": "en",
            "action": "copy",
            "source_type_id": str(source_id),
            "source_language": "en",
        },
    )
    assert resp.status_code == 302

    with app.app_context():
        tpl = PreworkTemplate.query.filter_by(
            workshop_type_id=dest_id, language="en"
        ).first()
        assert tpl is not None
        assert tpl.info_html == "source info"
        questions = sorted(tpl.questions, key=lambda q: q.position)
        assert len(questions) == 1
        assert questions[0].text == "Source question"
        assert questions[0].kind == "LIST"
        assert questions[0].min_items == 2
        assert questions[0].max_items == 4

def test_workshop_view_shows_prework_status(app_context):
    app = app_context
    sess, facilitator, submitted_participant, pending_participant = _seed_session()
    with app.app_context():
        db.session.add(
            PreworkInvite(
                session_id=sess.id,
                participant_id=submitted_participant.id,
                sender_id=facilitator.id,
                sent_at=datetime.utcnow(),
            )
        )
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as sess_data:
        sess_data["user_id"] = facilitator.id
    resp = client.get(f"/workshops/{sess.id}")
    html = resp.get_data(as_text=True)
    assert "Sent " in html
    assert "Not sent" in html
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
    invites = PreworkInvite.query.filter_by(session_id=sess.id).all()
    assert len(invites) == 1
    assert invites[0].participant_id == pending_participant.id
    assert invites[0].sender_id == facilitator.id
    assert invites[0].sent_at is not None
    with app.app_context():
        session_obj = Session.query.get(sess.id)
        assert session_obj.info_sent is True
        assert session_obj.info_sent_at is not None


def test_send_prework_uses_session_language(app_context, monkeypatch):
    app = app_context
    with app.app_context():
        facilitator = User(email="langfac@example.com", is_kt_delivery=True)
        facilitator.set_password("pw")
        wt = WorkshopType(
            code="LANG",
            name="Language",
            cert_series="fn",
            supported_languages=["en", "es"],
        )
        tpl_en = PreworkTemplate(workshop_type=wt, language="en")
        tpl_es = PreworkTemplate(workshop_type=wt, language="es")
        q_en = PreworkQuestion(template=tpl_en, position=1, text="English prompt", kind="TEXT")
        q_es = PreworkQuestion(template=tpl_es, position=1, text="Spanish prompt", kind="TEXT")
        session = Session(
            title="Idioma",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            daily_start_time=time(9, 0),
            workshop_language="es",
            lead_facilitator=facilitator,
        )
        participant = Participant(full_name="Learner", email="learner@example.com")
        db.session.add_all(
            [
                facilitator,
                wt,
                tpl_en,
                tpl_es,
                q_en,
                q_es,
                session,
                participant,
            ]
        )
        db.session.flush()
        db.session.add(
            SessionParticipant(session_id=session.id, participant_id=participant.id)
        )
        db.session.commit()
        sess_id = session.id
        facilitator_id = facilitator.id

    sent_to: list[str] = []

    def fake_send(to, subject, body, html):
        sent_to.append(to)
        return {"ok": True}

    monkeypatch.setattr(emailer, "send", fake_send)

    client = app.test_client()
    with client.session_transaction() as sess_data:
        sess_data["user_id"] = facilitator_id

    resp = client.post(
        f"/sessions/{sess_id}/prework",
        data={"action": "send_all"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert sent_to == ["learner@example.com"]
    with app.app_context():
        assignment = PreworkAssignment.query.filter_by(session_id=sess_id).first()
        assert assignment is not None
        assert assignment.template is not None
        assert assignment.template.language == "es"
        snapshot_questions = assignment.snapshot_json.get("questions") or []
        assert snapshot_questions and snapshot_questions[0]["text"] == "Spanish prompt"
    invites = PreworkInvite.query.filter_by(session_id=sess_id).all()
    assert len(invites) == 1
    assert invites[0].sender_id == facilitator_id
    session_obj = Session.query.get(sess_id)
    assert session_obj.info_sent is True
    assert session_obj.info_sent_at is not None


def test_workshop_view_shows_delivered_button(app_context):
    app = app_context
    sess, facilitator, *_rest = _seed_session(with_completion=False)
    client = app.test_client()
    with client.session_transaction() as sess_data:
        sess_data["user_id"] = facilitator.id
    resp = client.get(f"/workshops/{sess.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<button type="submit" class="btn btn-success">Delivered</button>' in html


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


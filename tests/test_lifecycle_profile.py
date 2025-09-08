import os
import sys
from datetime import date, timedelta

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import (
    User,
    WorkshopType,
    Session,
    Participant,
    SessionParticipant,
    ParticipantAccount,
)
from app.routes.sessions import _cb
from app.utils.provisioning import provision_participant_accounts_for_session


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login_admin(client, admin_id):
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id


def test_cb_helper():
    assert _cb("yes")
    assert _cb("On")
    assert not _cb("0")
    assert not _cb(None)


def test_delivered_gating(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        sess = Session(title="S1", workshop_type=wt, end_date=date.today() + timedelta(days=1))
        db.session.add_all([admin, wt, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client = app.test_client()
    login_admin(client, admin_id)
    client.post(f"/sessions/{session_id}/edit", data={"delivered": "1"})
    with app.app_context():
        sess = db.session.get(Session, session_id)
        assert not sess.delivered


def test_finalize_gating(app):
    with app.app_context():
        admin = User(email="adm@example.com", is_app_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        sess = Session(title="S1", workshop_type=wt, end_date=date.today())
        db.session.add_all([admin, wt, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client = app.test_client()
    login_admin(client, admin_id)
    client.post(f"/sessions/{session_id}/finalize")
    with app.app_context():
        sess = db.session.get(Session, session_id)
        assert not sess.finalized


def test_lifecycle_hidden_on_new(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        db.session.add_all([admin, wt])
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login_admin(client, admin_id)
    resp = client.get("/sessions/new")
    assert b"Lifecycle" not in resp.data


def test_certificate_name_defaults(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        sess = Session(title="S1", workshop_type=wt, end_date=date.today(), ready_for_delivery=True)
        part = Participant(email="p@example.com", full_name="P One")
        db.session.add_all([admin, wt, sess, part])
        db.session.commit()
        link = SessionParticipant(session_id=sess.id, participant_id=part.id)
        db.session.add(link)
        db.session.commit()
        provision_participant_accounts_for_session(sess.id)
        acct = ParticipantAccount.query.filter_by(email="p@example.com").one()
        assert acct.certificate_name == "P One"

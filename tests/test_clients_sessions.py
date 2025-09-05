import os
import sys
from datetime import date

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import (
    Client,
    Participant,
    ParticipantAccount,
    Session,
    SessionParticipant,
    User,
    WorkshopType,
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


def test_client_unique_name(app):
    with app.app_context():
        c1 = Client(name="Acme", status="active")
        db.session.add(c1)
        db.session.commit()
        c2 = Client(name="acme", status="active")
        db.session.add(c2)
        with pytest.raises(Exception):
            db.session.commit()


def test_session_form_shows_client_crm(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True)
        admin.set_password("x")
        crm = User(email="crm@example.com")
        wt = WorkshopType(code="WT", short_code="WT", name="WT")
        client = Client(name="ClientA", status="active", crm=crm)
        db.session.add_all([admin, crm, wt, client])
        db.session.commit()
        sess = Session(title="S1", workshop_type=wt, client_id=client.id)
        db.session.add(sess)
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client_tc = app.test_client()
    with client_tc.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client_tc.get(f"/sessions/{session_id}/edit")
    assert b"crm@example.com" in resp.data


def test_csa_add_remove_participants(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", short_code="WT", name="WT")
        sess = Session(title="S1", workshop_type=wt, end_date=date.today())
        db.session.add_all([admin, wt, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    admin_client = app.test_client()
    with admin_client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    admin_client.post(
        f"/sessions/{session_id}/assign-csa", data={"email": "csa@example.com"}
    )
    with app.app_context():
        account = db.session.query(ParticipantAccount).filter_by(email="csa@example.com").one()
    csa_client = app.test_client()
    with csa_client.session_transaction() as sess_tx:
        sess_tx["participant_account_id"] = account.id
    resp = csa_client.post(
        f"/sessions/{session_id}/participants/add",
        data={"full_name": "P1", "email": "p1@example.com"},
    )
    assert resp.status_code == 302
    with app.app_context():
        participant = db.session.query(Participant).filter_by(email="p1@example.com").one()
        part_id = participant.id
        sess_obj = db.session.get(Session, session_id)
        sess_obj.delivered = True
        db.session.commit()
    resp = csa_client.post(
        f"/sessions/{session_id}/participants/{part_id}/remove",
    )
    assert resp.status_code == 403


def test_smtp_test_route(app, monkeypatch):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True)
        admin.set_password("x")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    def fake_send(to, subject, body):
        return {"ok": True}

    monkeypatch.setattr("app.routes.settings_mail.send", fake_send)
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client.post("/mail-settings/test", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Test email sent" in resp.data


def test_session_detail_redirects_when_not_logged_in(app):
    with app.app_context():
        wt = WorkshopType(code="WT", short_code="WT", name="WT")
        sess = Session(
            title="S1",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
        )
        db.session.add_all([wt, sess])
        db.session.commit()
        sess_id = sess.id
    client = app.test_client()
    resp = client.get(f"/sessions/{sess_id}", follow_redirects=True)
    assert b"Please log in to administer this session." in resp.data

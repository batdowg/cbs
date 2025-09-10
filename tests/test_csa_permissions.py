import os
from datetime import date, time, timedelta

import pytest

from app.app import create_app, db
from app.models import (
    User,
    WorkshopType,
    Session,
    ParticipantAccount,
    Participant,
    SessionParticipant,
    Certificate,
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
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        kcrm = User(email="kcrm@example.com", is_kcrm=True)
        csa_acc = ParticipantAccount(email="csa@example.com", full_name="CSA", is_active=True)
        today = date.today()
        sess_open = Session(
            title="Open",
            workshop_type=wt,
            start_date=today,
            end_date=today,
            daily_start_time=time(9, 0),
            timezone="UTC",
            csa_account=csa_acc,
        )
        sess_ready = Session(
            title="Ready",
            workshop_type=wt,
            start_date=today,
            end_date=today,
            daily_start_time=time(9, 0),
            timezone="UTC",
            ready_for_delivery=True,
            csa_account=csa_acc,
        )
        db.session.add_all([wt, admin, kcrm, csa_acc, sess_open, sess_ready])
        db.session.commit()
        return admin.id, kcrm.id, csa_acc.id, sess_open.id, sess_ready.id


def _login_user(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _login_csa(client, account_id):
    with client.session_transaction() as sess:
        sess["participant_account_id"] = account_id


def test_csa_can_manage_before_ready(app):
    admin_id, kcrm_id, csa_id, open_id, ready_id = _setup(app)
    client = app.test_client()
    _login_csa(client, csa_id)

    resp = client.post(
        f"/sessions/{open_id}/participants/add",
        data={"email": "p@example.com", "full_name": "P"},
    )
    assert resp.status_code == 302
    resp = client.get(f"/sessions/{open_id}")
    assert b"Add Participant" in resp.data
    assert b"Prework" not in resp.data


def test_csa_blocked_after_ready(app, caplog):
    admin_id, kcrm_id, csa_id, open_id, ready_id = _setup(app)
    client = app.test_client()
    _login_csa(client, csa_id)

    caplog.set_level("INFO")
    resp = client.post(
        f"/sessions/{ready_id}/participants/add",
        data={"email": "p2@example.com", "full_name": "P2"},
    )
    assert resp.status_code == 403
    assert any("blocked-after-ready" in r.getMessage() for r in caplog.records)
    resp = client.get(f"/sessions/{ready_id}")
    assert b"Participant changes closed" in resp.data


def test_csa_prework_and_edit_forbidden(app):
    admin_id, kcrm_id, csa_id, open_id, ready_id = _setup(app)
    client = app.test_client()
    _login_csa(client, csa_id)

    resp = client.get(f"/sessions/{open_id}/prework")
    assert resp.status_code in (302, 403)
    resp = client.get(f"/sessions/{open_id}/edit")
    assert resp.status_code in (302, 403)


def test_admin_kcrm_can_add(app):
    admin_id, kcrm_id, csa_id, open_id, ready_id = _setup(app)
    client = app.test_client()

    _login_user(client, admin_id)
    resp = client.post(
        f"/sessions/{open_id}/participants/add",
        data={"email": "a1@example.com"},
    )
    assert resp.status_code == 302

    _login_user(client, kcrm_id)
    resp = client.post(
        f"/sessions/{open_id}/participants/add",
        data={"email": "a2@example.com"},
    )
    assert resp.status_code == 302


def test_csa_can_see_certificate(app):
    with app.app_context():
        admin_id, kcrm_id, csa_id, open_id, ready_id = _setup(app)
        sess = db.session.get(Session, ready_id)
        participant = Participant(email="p3@example.com", full_name="P3")
        db.session.add(participant)
        db.session.flush()
        link = SessionParticipant(session_id=sess.id, participant_id=participant.id)
        cert = Certificate(
            session_id=sess.id,
            participant_id=participant.id,
            certificate_name="P3",
            workshop_name="Ready",
            workshop_date=date.today(),
            pdf_path="dummy.pdf",
        )
        db.session.add_all([link, cert])
        db.session.commit()
        csa_account_id = csa_id
        session_id = sess.id
    client = app.test_client()
    _login_csa(client, csa_account_id)
    resp = client.get(f"/sessions/{session_id}")
    html = resp.data.decode()
    assert 'href="/certificates/dummy.pdf"' in html
    assert "Certificate" in html

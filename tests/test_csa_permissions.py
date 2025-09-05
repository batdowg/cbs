import os
from datetime import date, time, timedelta

import pytest

from app.app import create_app, db
from app.models import User, WorkshopType, Session, ParticipantAccount


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
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        kcrm = User(email="kcrm@example.com", is_kcrm=True)
        csa_acc = ParticipantAccount(email="csa@example.com", full_name="CSA", is_active=True)
        future = date.today() + timedelta(days=1)
        past = date.today() - timedelta(days=1)
        sess_future = Session(
            title="F",
            workshop_type=wt,
            start_date=future,
            end_date=future,
            daily_start_time=time(9, 0),
            timezone="UTC",
            csa_account=csa_acc,
        )
        sess_past = Session(
            title="P",
            workshop_type=wt,
            start_date=past,
            end_date=past,
            daily_start_time=time(9, 0),
            timezone="UTC",
            csa_account=csa_acc,
        )
        db.session.add_all([wt, admin, kcrm, csa_acc, sess_future, sess_past])
        db.session.commit()
        return admin.id, kcrm.id, csa_acc.id, sess_future.id, sess_past.id


def _login_user(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _login_csa(client, account_id):
    with client.session_transaction() as sess:
        sess["participant_account_id"] = account_id


def test_csa_can_manage_before_start(app):
    admin_id, kcrm_id, csa_id, future_id, past_id = _setup(app)
    client = app.test_client()
    _login_csa(client, csa_id)

    resp = client.post(
        f"/sessions/{future_id}/participants/add",
        data={"email": "p@example.com", "full_name": "P"},
    )
    assert resp.status_code == 302
    resp = client.get(f"/sessions/{future_id}")
    assert b"Add Participant" in resp.data
    assert b"Prework" not in resp.data


def test_csa_blocked_after_start(app, caplog):
    admin_id, kcrm_id, csa_id, future_id, past_id = _setup(app)
    client = app.test_client()
    _login_csa(client, csa_id)

    caplog.set_level("INFO")
    resp = client.post(
        f"/sessions/{past_id}/participants/add",
        data={"email": "p2@example.com", "full_name": "P2"},
    )
    assert resp.status_code == 403
    assert any("blocked-after-start" in r.getMessage() for r in caplog.records)
    resp = client.get(f"/sessions/{past_id}")
    assert b"Participant changes closed" in resp.data


def test_csa_prework_and_edit_forbidden(app):
    admin_id, kcrm_id, csa_id, future_id, past_id = _setup(app)
    client = app.test_client()
    _login_csa(client, csa_id)

    resp = client.get(f"/sessions/{future_id}/prework")
    assert resp.status_code in (302, 403)
    resp = client.get(f"/sessions/{future_id}/edit")
    assert resp.status_code in (302, 403)


def test_admin_kcrm_can_add(app):
    admin_id, kcrm_id, csa_id, future_id, past_id = _setup(app)
    client = app.test_client()

    _login_user(client, admin_id)
    resp = client.post(
        f"/sessions/{future_id}/participants/add",
        data={"email": "a1@example.com"},
    )
    assert resp.status_code == 302

    _login_user(client, kcrm_id)
    resp = client.post(
        f"/sessions/{future_id}/participants/add",
        data={"email": "a2@example.com"},
    )
    assert resp.status_code == 302

import os
import logging
from datetime import date

import pytest

from app.app import create_app, db
from app.models import User, WorkshopType, Session, ParticipantAccount
from app import emailer
from app.constants import DEFAULT_CSA_PASSWORD


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
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", short_code="WT", name="WT")
        sess = Session(title="S1", workshop_type=wt, start_date=date(2100, 1, 1), end_date=date(2100, 1, 1))
        db.session.add_all([admin, wt, sess])
        db.session.commit()
        return admin.id, sess.id


def _login(client, admin_id):
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id


def _count_logs(caplog):
    return sum(1 for r in caplog.records if "csa-assign" in r.getMessage())


def test_csa_assign_email_logs(app, monkeypatch, caplog):
    admin_id, sess_id = _setup(app)
    client = app.test_client()
    _login(client, admin_id)

    monkeypatch.setattr(emailer, "send", lambda *a, **k: {"ok": True, "detail": "sent"})

    caplog.set_level(logging.INFO)
    resp = client.post(f"/sessions/{sess_id}/assign-csa", data={"email": "csa1@example.com"})
    assert resp.status_code == 302
    assert _count_logs(caplog) == 1

    caplog.clear()
    resp = client.post(f"/sessions/{sess_id}/assign-csa", data={"email": "csa1@example.com"})
    assert resp.status_code == 302
    assert _count_logs(caplog) == 0

    caplog.clear()
    resp = client.post(f"/sessions/{sess_id}/assign-csa", data={"email": "csa2@example.com"})
    assert resp.status_code == 302
    assert _count_logs(caplog) == 1


def test_assign_csa_creates_account_with_password(app, monkeypatch):
    admin_id, sess_id = _setup(app)
    client = app.test_client()
    _login(client, admin_id)

    sent = {}

    def fake_send(to, subject, body, html):
        sent["body"] = body
        return {"ok": True}

    monkeypatch.setattr(emailer, "send", fake_send)

    resp = client.post(
        f"/sessions/{sess_id}/assign-csa", data={"email": "newcsa@example.com"}
    )
    assert resp.status_code == 302
    with app.app_context():
        account = (
            db.session.query(ParticipantAccount)
            .filter_by(email="newcsa@example.com")
            .one()
        )
        assert account.check_password(DEFAULT_CSA_PASSWORD)
    assert "newcsa@example.com" in sent["body"]
    assert DEFAULT_CSA_PASSWORD in sent["body"]


def test_assign_csa_existing_account_password_unchanged(app, monkeypatch):
    admin_id, sess_id = _setup(app)
    client = app.test_client()
    _login(client, admin_id)

    with app.app_context():
        account = ParticipantAccount(
            email="existing@example.com", full_name="Ex", is_active=True
        )
        account.set_password("orig")
        db.session.add(account)
        db.session.commit()

    monkeypatch.setattr(emailer, "send", lambda *a, **k: {"ok": True})

    resp = client.post(
        f"/sessions/{sess_id}/assign-csa", data={"email": "existing@example.com"}
    )
    assert resp.status_code == 302
    with app.app_context():
        account = (
            db.session.query(ParticipantAccount)
            .filter_by(email="existing@example.com")
            .one()
        )
        assert account.check_password("orig")

import os
import logging
from datetime import date

import pytest

from app.app import create_app, db
from app.models import User, WorkshopType, Session
from app import emailer


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
        wt = WorkshopType(code="WT", name="WT")
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

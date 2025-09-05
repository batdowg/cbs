import os
from datetime import date, time

import pytest

from app.app import create_app, db
from app.models import User, Client, WorkshopType, Session


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
        client = Client(name="ClientA", status="active")
        db.session.add_all([admin, wt, client])
        db.session.commit()
        return admin.id, wt.id, client.id


def _login(client, admin_id):
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id


def _base_form(client_id, wt_id):
    return {
        "title": "S1",
        "client_id": str(client_id),
        "region": "NA",
        "workshop_type_id": str(wt_id),
        "delivery_type": "Onsite",
        "language": "English",
        "workshop_language": "en",
        "capacity": "16",
        "daily_start_time": "09:00",
        "daily_end_time": "17:00",
    }


def test_end_date_rule(app):
    admin_id, wt_id, client_id = _setup(app)
    client = app.test_client()
    _login(client, admin_id)
    form = _base_form(client_id, wt_id)
    form.update({"start_date": "2100-01-02", "end_date": "2100-01-01"})
    resp = client.post("/sessions/new", data=form)
    assert resp.status_code == 400
    assert b"End date must be the same day or after the start date" in resp.data
    with app.app_context():
        assert Session.query.count() == 0
    form["end_date"] = "2100-01-02"
    resp = client.post("/sessions/new", data=form, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        sess = Session.query.one()
        assert sess.end_date == date(2100, 1, 2)
        assert isinstance(sess.daily_start_time, time)


def test_past_start_requires_ack(app):
    admin_id, wt_id, client_id = _setup(app)
    client = app.test_client()
    _login(client, admin_id)
    form = _base_form(client_id, wt_id)
    form.update({"start_date": "2000-01-01", "end_date": "2000-01-02"})
    resp = client.post("/sessions/new", data=form)
    assert resp.status_code == 400
    assert b"The selected start date is in the past" in resp.data
    form["ack_past"] = "true"
    resp = client.post("/sessions/new", data=form, follow_redirects=False)
    assert resp.status_code == 302


def test_times_preserved_on_error(app):
    admin_id, wt_id, client_id = _setup(app)
    client = app.test_client()
    _login(client, admin_id)
    form = _base_form(client_id, wt_id)
    form.update({
        "start_date": "2100-01-02",
        "end_date": "2100-01-01",
        "daily_start_time": "09:30",
        "daily_end_time": "17:15",
    })
    resp = client.post("/sessions/new", data=form)
    assert resp.status_code == 400
    assert b'value="09:30"' in resp.data
    assert b'value="17:15"' in resp.data


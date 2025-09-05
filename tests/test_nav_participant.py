import os
from datetime import date, time

import pytest

from app.app import create_app, db
from app.models import WorkshopType, Session, ParticipantAccount


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
        acc = ParticipantAccount(email="p@example.com", full_name="P", is_active=True)
        sess = Session(
            title="S",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            daily_start_time=time(9, 0),
            timezone="UTC",
        )
        db.session.add_all([wt, acc, sess])
        db.session.commit()
        return acc.id


def _login(client, account_id):
    with client.session_transaction() as sess:
        sess["participant_account_id"] = account_id


def test_participant_nav_simple(app):
    acc_id = _setup(app)
    client = app.test_client()
    _login(client, acc_id)
    resp = client.get("/my-workshops")
    assert b"Home" in resp.data
    assert b"My Workshops" in resp.data
    assert b"My Sessions" not in resp.data
    assert b"My Profile" in resp.data
    assert b"Logout" in resp.data

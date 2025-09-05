import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import User, ParticipantAccount, Session


def login(client, user_id):
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['actor_kind'] = 'user'


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_user_create_blocked(app):
    with app.app_context():
        pa = ParticipantAccount(email="p@example.com", full_name="P", is_active=True)
        pa.set_password("pw")
        admin = User(email="admin@example.com", is_app_admin=True, region="NA")
        admin.set_password("pw")
        db.session.add_all([pa, admin])
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        "/users/new",
        data={"email": "p@example.com", "region": "NA"},
        follow_redirects=True,
    )
    assert b"Promote to a user account" in resp.data


def test_participant_create_blocked_by_user(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, region="NA")
        admin.set_password("pw")
        staff = User(email="staff@example.com", is_app_admin=False, region="NA")
        staff.set_password("pw")
        sess = Session(
            title="S", start_date=date.today(), end_date=date.today(), timezone="UTC"
        )
        db.session.add_all([admin, staff, sess])
        db.session.commit()
        admin_id = admin.id
        sess_id = sess.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        f"/sessions/{sess_id}/participants/add",
        data={"email": "staff@example.com", "full_name": "Test"},
        follow_redirects=True,
    )
    assert b"Participant added" in resp.data
    with app.app_context():
        assert (
            ParticipantAccount.query.filter_by(email="staff@example.com").first()
            is None
        )

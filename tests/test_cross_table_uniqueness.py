import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import User, ParticipantAccount, Session, Participant


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


def test_user_create_allowed(app):
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
    assert b"Email already exists" not in resp.data
    with app.app_context():
        assert User.query.filter_by(email="p@example.com").first() is not None


def test_participant_create_seeds_from_staff_user(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, region="NA")
        admin.set_password("pw")
        staff = User(
            email="staff@example.com", full_name="Staff User", title="Dr", region="NA"
        )
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
        data={"email": "staff@example.com"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        participant = Participant.query.filter_by(email="staff@example.com").one()
        account = ParticipantAccount.query.filter_by(email="staff@example.com").one()
        assert participant.full_name == "Staff User"
        assert participant.title == "Dr"
        assert account.full_name == "Staff User"
        assert account.certificate_name == "Staff User"

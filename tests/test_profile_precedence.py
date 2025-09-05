import os
import sys
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import User, ParticipantAccount


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login_user(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def login_participant(client, account_id):
    with client.session_transaction() as sess:
        sess["participant_account_id"] = account_id


def test_staff_profile_uses_user_fields(app):
    with app.app_context():
        u = User(email="staff@example.com", full_name="Staff Name", title="Boss")
        u.set_password("x")
        pa = ParticipantAccount(email="staff@example.com", full_name="Learner Name", certificate_name="Cert")
        pa.set_password("y")
        db.session.add_all([u, pa])
        db.session.commit()
        uid = u.id
    client = app.test_client()
    login_user(client, uid)
    resp = client.get("/profile")
    assert b"Staff Name" in resp.data
    assert b"Learner Name" not in resp.data
    assert b"Title" in resp.data
    assert b"Certificate Name" not in resp.data


def test_learner_profile_uses_participant_fields(app):
    with app.app_context():
        pa = ParticipantAccount(email="learner@example.com", full_name="Learner One", certificate_name="Cert")
        pa.set_password("x")
        db.session.add(pa)
        db.session.commit()
        aid = pa.id
    client = app.test_client()
    login_participant(client, aid)
    resp = client.get("/profile")
    assert b"Learner One" in resp.data
    assert b"Certificate Name" in resp.data
    assert b"Title" not in resp.data

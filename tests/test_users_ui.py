import os
import pytest

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


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_new_user_form_has_no_staff_checkbox(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.get("/users/new")
    assert b"KT Staff" not in resp.data


def test_promote_interstitial_mentions_participant_CSA(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        p = ParticipantAccount(email="p@example.com", full_name="P")
        db.session.add_all([admin, p])
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        "/users/new",
        data={"email": "p@example.com", "full_name": "P", "region": "NA"},
    )
    assert b"Promote to a user account" in resp.data

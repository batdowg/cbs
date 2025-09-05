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


def test_admin_can_promote_participant_to_user_with_roles(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        p = ParticipantAccount(email="p@example.com", full_name="P")
        db.session.add_all([admin, p])
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        "/users/promote",
        data={"email": "p@example.com", "is_admin": "1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="p@example.com").first()
        assert user and user.is_admin


def test_forbid_promote_with_contractor_plus_other_role(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        p = ParticipantAccount(email="p@example.com", full_name="P")
        db.session.add_all([admin, p])
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        "/users/promote",
        data={"email": "p@example.com", "is_admin": "1", "is_kt_contractor": "1"},
        follow_redirects=True,
    )
    assert b"Invalid role combination" in resp.data
    with app.app_context():
        assert User.query.filter_by(email="p@example.com").count() == 0


def test_non_admin_cannot_promote(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        non = User(email="user@example.com")
        p = ParticipantAccount(email="p@example.com", full_name="P")
        db.session.add_all([admin, non, p])
        db.session.commit()
        non_id = non.id
    client = app.test_client()
    login(client, non_id)
    assert client.post("/users/promote", data={"email": "p@example.com"}).status_code == 403

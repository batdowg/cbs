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


def test_promote_requires_admin(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        user = User(email="user@example.com")
        p = ParticipantAccount(email="p@example.com", full_name="P")
        db.session.add_all([admin, user, p])
        db.session.commit()
        admin_id = admin.id
        user_id = user.id
    client = app.test_client()
    login(client, user_id)
    assert client.post("/users/promote", data={"email": "p@example.com"}).status_code == 403
    login(client, admin_id)
    resp = client.post(
        "/users/promote",
        data={"email": "p@example.com", "region": "NA", "is_kt_staff": "1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

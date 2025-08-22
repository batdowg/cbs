import os
import pytest

import os
import pytest

from app.app import create_app, db
from app.models import User, UserAuditLog


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login(client, user_id):
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = user_id


def test_edit_user_name_region(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, full_name="Admin", region="NA")
        admin.set_password("x")
        target = User(email="user@example.com", full_name="User", region="EU")
        db.session.add_all([admin, target])
        db.session.commit()
        admin_id = admin.id
        target_id = target.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        f"/users/{target_id}/edit",
        data={"email": "hax@example.com", "full_name": "User2", "region": "SEA"},
        follow_redirects=True,
    )
    assert b"User updated." in resp.data
    with app.app_context():
        user = db.session.get(User, target_id)
        assert user.email == "user@example.com"
        assert user.full_name == "User2"
        assert user.region == "SEA"
        logs = db.session.query(UserAuditLog).filter_by(target_user_id=target_id).all()
        assert len(logs) == 2
        fields = {l.field for l in logs}
        assert fields == {"full_name", "region"}


def test_edit_user_forbidden(app):
    with app.app_context():
        u1 = User(email="u1@example.com")
        u2 = User(email="u2@example.com")
        db.session.add_all([u1, u2])
        db.session.commit()
        u1_id = u1.id
        u2_id = u2.id
    client = app.test_client()
    login(client, u1_id)
    resp = client.get(f"/users/{u2_id}/edit")
    assert resp.status_code == 403

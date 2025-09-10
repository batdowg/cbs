import os
import pytest

from app.app import create_app, db
from app.models import User


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
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_badges_admin_access(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.get("/settings/badges")
    assert resp.status_code == 200
    assert b"Badges (placeholder)" in resp.data


def test_badges_blocked_for_crm(app):
    with app.app_context():
        crm = User(email="crm@example.com", is_kcrm=True)
        db.session.add(crm)
        db.session.commit()
        crm_id = crm.id
    client = app.test_client()
    login(client, crm_id)
    resp = client.get("/settings/badges")
    assert resp.status_code == 403

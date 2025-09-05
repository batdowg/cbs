import os
import pytest

from app.app import create_app, db
from app.models import User


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


def test_admin_can_demote_regular_user_to_contractor_stripping_other_roles(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        target = User(email="u@example.com", is_admin=True, is_kcrm=True)
        db.session.add_all([admin, target])
        db.session.commit()
        admin_id = admin.id
        target_id = target.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(f"/users/{target_id}/demote-contractor", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        t = db.session.get(User, target_id)
        assert t.is_kt_contractor
        assert not t.is_admin and not t.is_kcrm


def test_cannot_demote_sys_admin(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        sys = User(email="sys@example.com", is_app_admin=True)
        db.session.add_all([admin, sys])
        db.session.commit()
        admin_id = admin.id
        sys_id = sys.id
    client = app.test_client()
    login(client, admin_id)
    assert client.post(f"/users/{sys_id}/demote-contractor").status_code == 403


def test_cannot_demote_self(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login(client, admin_id)
    assert client.post(f"/users/{admin_id}/demote-contractor").status_code == 403


def test_last_admin_guard(app):
    with app.app_context():
        sys = User(email="sys@example.com", is_app_admin=True)
        admin = User(email="admin@example.com", is_admin=True)
        db.session.add_all([sys, admin])
        db.session.commit()
        sys_id = sys.id
        admin_id = admin.id
    client = app.test_client()
    login(client, sys_id)
    resp = client.post(f"/users/{admin_id}/demote-contractor", follow_redirects=True)
    assert b"Cannot remove the last Admin" in resp.data
    with app.app_context():
        a = db.session.get(User, admin_id)
        assert a.is_admin

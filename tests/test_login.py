import os
import pytest

from app.app import create_app, db
from app.models import User, ParticipantAccount, AuditLog


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_staff_login(app):
    with app.app_context():
        u = User(email="staff@example.com", is_app_admin=True, region="NA")
        u.set_password("pw")
        db.session.add(u)
        db.session.commit()
    client = app.test_client()
    resp = client.post("/login", data={"email": "staff@example.com", "password": "pw"}, follow_redirects=True)
    assert resp.request.path == "/home"


def test_internal_email_login(app):
    with app.app_context():
        u = User(email="c@c.c", is_app_admin=True, region="NA")
        u.set_password("pw")
        db.session.add(u)
        db.session.commit()
    client = app.test_client()
    resp = client.post("/login", data={"email": "c@c.c", "password": "pw"}, follow_redirects=True)
    assert resp.request.path == "/home"


def test_participant_login(app):
    with app.app_context():
        p = ParticipantAccount(email="learner@example.com", full_name="L", is_active=True)
        p.set_password("pw")
        db.session.add(p)
        db.session.commit()
    client = app.test_client()
    resp = client.post("/login", data={"email": "learner@example.com", "password": "pw"}, follow_redirects=True)
    assert resp.request.path == "/my-workshops"


def test_unknown_email(app):
    client = app.test_client()
    resp = client.post("/login", data={"email": "none@example.com", "password": "x"}, follow_redirects=True)
    assert resp.request.path == "/login"
    assert b"No account with that email." in resp.data


def test_wrong_password(app):
    with app.app_context():
        u = User(email="user@example.com", is_app_admin=True, region="NA")
        u.set_password("good")
        db.session.add(u)
        db.session.commit()
    client = app.test_client()
    resp = client.post("/login", data={"email": "user@example.com", "password": "bad"}, follow_redirects=True)
    assert resp.request.path == "/login"
    assert b"Invalid email or password." in resp.data


def test_conflict_prefers_user(app):
    with app.app_context():
        u = User(email="both@example.com", is_app_admin=True, region="NA")
        u.set_password("pw")
        p = ParticipantAccount(email="both@example.com", full_name="B", is_active=True)
        p.set_password("pw")
        db.session.add_all([u, p])
        db.session.commit()
    client = app.test_client()
    resp = client.post("/login", data={"email": "both@example.com", "password": "pw"}, follow_redirects=True)
    assert resp.request.path == "/home"
    assert b"Signed in as staff account; learner account also exists." in resp.data
    with app.app_context():
        log = db.session.query(AuditLog).filter_by(action="login_dupe_email").first()
        assert log is not None


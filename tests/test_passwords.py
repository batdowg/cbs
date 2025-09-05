import os
import re
import time
import pytest
from itsdangerous import URLSafeTimedSerializer
from datetime import date

from app.app import create_app, db
from app.models import (
    User,
    Session,
    Participant,
    ParticipantAccount,
    SessionParticipant,
    AuditLog,
)
from app.utils.provisioning import provision_participant_accounts_for_session
from app.utils import accounts as acct_utils
from app.constants import DEFAULT_PARTICIPANT_PASSWORD


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login_user(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_manual_participant_create_login(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, region="NA")
        admin.set_password("x")
        db.session.add(admin)
        sess = Session(title="Test", start_date=date(2024,1,1), end_date=date(2024,1,2), region="NA")
        db.session.add(sess)
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client = app.test_client()
    login_user(client, admin_id)
    resp = client.post(
        f"/sessions/{session_id}/participants/add",
        data={
            "full_name": "Learner",
            "email": "learner@example.com",
            "title": "Mr",
        },
        follow_redirects=True,
    )
    assert b"Participant added" in resp.data
    client.get("/logout")
    # login as participant
    with app.app_context():
        participant = Participant.query.filter_by(email="learner@example.com").first()
        acct, temp_pw = acct_utils.ensure_participant_account(participant, {})
        db.session.commit()
        assert temp_pw == DEFAULT_PARTICIPANT_PASSWORD
    resp = client.post(
        "/login",
        data={"email": "learner@example.com", "password": temp_pw},
        follow_redirects=True,
    )
    assert resp.request.path == "/my-workshops"


def test_provision_sets_default_password(app):
    with app.app_context():
        part = Participant(email="p@example.com", full_name="P")
        sess = Session(
            title="S",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            region="NA",
        )
        db.session.add_all([part, sess])
        db.session.flush()
        link = SessionParticipant(session_id=sess.id, participant_id=part.id)
        db.session.add(link)
        db.session.commit()
        summary = provision_participant_accounts_for_session(sess.id)
        acct = ParticipantAccount.query.filter_by(email="p@example.com").one()
        assert summary["created"] == 1
        assert acct.check_password(DEFAULT_PARTICIPANT_PASSWORD)


def test_provision_keeps_password(app):
    with app.app_context():
        acct = ParticipantAccount(email="p@example.com", full_name="P", is_active=True)
        acct.set_password("orig")
        part = Participant(email="p@example.com", full_name="P", account=acct)
        sess = Session(title="S", start_date=date(2024,1,1), end_date=date(2024,1,2), region="NA")
        db.session.add_all([acct, part, sess])
        db.session.flush()
        link = SessionParticipant(session_id=sess.id, participant_id=part.id)
        db.session.add(link)
        db.session.commit()
        orig = acct.password_hash
        summary = provision_participant_accounts_for_session(sess.id)
        db.session.refresh(acct)
        assert summary["already_active"] == 1
        assert acct.password_hash == orig


def test_forgot_password_flow(app):
    with app.app_context():
        user = User(email="u@example.com", full_name="U", region="NA")
        user.set_password("old")
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    resp = client.post(
        "/forgot-password",
        data={"email": "u@example.com"},
        follow_redirects=True,
    )
    m = re.search(b"Dev only token:</strong> ([A-Za-z0-9._-]+)", resp.data)
    assert m
    token = m.group(1).decode()
    client.post(
        "/reset-password",
        data={"token": token, "password": "newpass", "password_confirm": "newpass"},
        follow_redirects=True,
    )
    resp = client.post(
        "/login",
        data={"email": "u@example.com", "password": "newpass"},
        follow_redirects=True,
    )
    assert resp.request.path == "/home"
    # invalid/expired token rejected
    resp = client.get("/reset-password?token=bad", follow_redirects=True)
    assert b"Invalid or expired token" in resp.data


def test_admin_set_password_logs(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, region="NA")
        admin.set_password("x")
        target = User(email="user2@example.com", full_name="User2", region="NA")
        db.session.add_all([admin, target])
        db.session.commit()
        admin_id = admin.id
        target_id = target.id
    client = app.test_client()
    login_user(client, admin_id)
    resp = client.post(
        f"/users/{target_id}/edit",
        data={"full_name": "User2", "region": "NA", "password": "abc", "password_confirm": "abc"},
        follow_redirects=True,
    )
    assert b"User updated" in resp.data
    with app.app_context():
        user = db.session.get(User, target_id)
        assert user.check_password("abc")
        log = db.session.query(AuditLog).filter_by(action="password_reset_admin").first()
        assert log is not None and log.user_id == admin_id


def test_add_staff_user_as_participant(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, region="NA")
        admin.set_password("x")
        staff = User(email="staff@example.com", full_name="Staff Member", region="NA")
        staff.set_password("y")
        sess = Session(title="Test", start_date=date(2024,1,1), end_date=date(2024,1,2), region="NA")
        db.session.add_all([admin, staff, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client = app.test_client()
    login_user(client, admin_id)
    resp = client.post(
        f"/sessions/{session_id}/participants/add",
        data={"full_name": "Staff Member", "email": "staff@example.com", "title": "Mr"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        participant = Participant.query.filter_by(email="staff@example.com").one()
        account = ParticipantAccount.query.filter_by(email="staff@example.com").one()
        assert participant.full_name == "Staff Member"
        assert participant.title == "Mr"
        assert account.full_name == "Staff Member"
        assert account.certificate_name == "Staff Member"

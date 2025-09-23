import os
import sys
from io import BytesIO

import pytest
from PIL import Image

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import User, ParticipantAccount


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv/uploads/profile_pics", exist_ok=True)
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
    assert b"Certificate Name" in resp.data


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


def test_staff_profile_sets_certificate_name(app):
    with app.app_context():
        u = User(email="x@example.com", full_name="Staff", title="Boss")
        u.set_password("x")
        db.session.add(u)
        db.session.commit()
        uid = u.id
    client = app.test_client()
    login_user(client, uid)
    resp = client.post(
        "/profile",
        data={
            "form": "profile",
            "full_name": "Staff",
            "certificate_name": "Cert Staff",
            "preferred_language": "en",
            "title": "Boss",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        pa = ParticipantAccount.query.filter_by(email="x@example.com").one()
        assert pa.certificate_name == "Cert Staff"


def _create_image_bytes(color=(30, 144, 255)):
    buf = BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_profile_updates_contact_fields_and_photo(app):
    with app.app_context():
        user = User(email="img@example.com", full_name="Img User", title="Lead")
        user.set_password("x")
        account = ParticipantAccount(email="img@example.com", full_name="Img User", is_active=True)
        db.session.add_all([user, account])
        db.session.commit()
        uid = user.id
    client = app.test_client()
    login_user(client, uid)
    image = _create_image_bytes()
    resp = client.post(
        "/profile",
        data={
            "form": "profile",
            "full_name": "Img User",
            "certificate_name": "Img Cert",
            "preferred_language": "en",
            "title": "Lead",
            "phone": "+1 555 1234",
            "city": "Austin",
            "state": "TX",
            "country": "USA",
            "profile_image": (image, "avatar.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Profile updated" in resp.data
    with app.app_context():
        user = db.session.get(User, uid)
        account = ParticipantAccount.query.filter_by(email="img@example.com").one()
        assert user.phone == "+1 555 1234"
        assert user.city == "Austin"
        assert user.state == "TX"
        assert user.country == "USA"
        assert account.phone == "+1 555 1234"
        assert account.city == "Austin"
        assert account.state == "TX"
        assert account.country == "USA"
        assert user.profile_image_path
        path = os.path.join("/srv", user.profile_image_path.lstrip("/"))
        assert os.path.isfile(path)


def test_profile_rejects_invalid_phone(app):
    with app.app_context():
        user = User(email="invalid@example.com", full_name="Invalid")
        user.set_password("x")
        db.session.add(user)
        db.session.commit()
        uid = user.id
    client = app.test_client()
    login_user(client, uid)
    resp = client.post(
        "/profile",
        data={
            "form": "profile",
            "full_name": "Invalid",
            "certificate_name": "Invalid",
            "preferred_language": "en",
            "title": "",
            "phone": "abc123",
            "city": "Austin",
            "state": "TX",
        },
        follow_redirects=True,
    )
    assert b"Phone number may include" in resp.data
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.phone is None


def test_profile_requires_location_components(app):
    with app.app_context():
        user = User(email="loc@example.com", full_name="Loc")
        user.set_password("x")
        db.session.add(user)
        db.session.commit()
        uid = user.id
    client = app.test_client()
    login_user(client, uid)
    resp = client.post(
        "/profile",
        data={
            "form": "profile",
            "full_name": "Loc",
            "certificate_name": "Loc",
            "preferred_language": "en",
            "title": "",
            "city": "",
            "state": "TX",
        },
        follow_redirects=True,
    )
    assert b"City is required" in resp.data


def test_profile_rejects_non_image_upload(app):
    with app.app_context():
        user = User(email="badfile@example.com", full_name="Bad File")
        user.set_password("x")
        db.session.add(user)
        db.session.commit()
        uid = user.id
    client = app.test_client()
    login_user(client, uid)
    resp = client.post(
        "/profile",
        data={
            "form": "profile",
            "full_name": "Bad File",
            "certificate_name": "Bad",
            "preferred_language": "en",
            "title": "",
            "profile_image": (BytesIO(b"not an image"), "avatar.txt"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Only PNG and JPG images are allowed" in resp.data


def test_profile_rejects_oversized_upload(app):
    with app.app_context():
        user = User(email="large@example.com", full_name="Large")
        user.set_password("x")
        db.session.add(user)
        db.session.commit()
        uid = user.id
    client = app.test_client()
    login_user(client, uid)
    big = BytesIO(b"a" * (2 * 1024 * 1024 + 10))
    resp = client.post(
        "/profile",
        data={
            "form": "profile",
            "full_name": "Large",
            "certificate_name": "Large",
            "preferred_language": "en",
            "title": "",
            "profile_image": (big, "avatar.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Image is larger than 2 MB" in resp.data

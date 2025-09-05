import os
import pytest

from app.app import create_app, db
from app.models import User, ParticipantAccount
from app.utils.nav import build_menu
from app.utils.acl import is_staff_user


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


def test_only_admins_can_access_user_create_edit_promote(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        non = User(email="non@example.com")
        p = ParticipantAccount(email="p@example.com", full_name="P")
        db.session.add_all([admin, non, p])
        db.session.commit()
        admin_id = admin.id
        non_id = non.id
        p_id = p.id
    client = app.test_client()
    login(client, non_id)
    assert client.get("/users/new").status_code == 403
    assert client.get(f"/users/{admin_id}/edit").status_code == 403
    assert client.post("/users/promote", data={"email": "p@example.com"}).status_code == 403
    login(client, admin_id)
    assert client.get("/users/new").status_code == 200
    assert client.get(f"/users/{non_id}/edit").status_code == 200
    assert client.post(
        "/users/promote", data={"email": "p@example.com", "region": "NA", "is_kt_staff": "1"}, follow_redirects=True
    ).status_code == 200


def test_contractor_cannot_be_combined_with_other_roles_on_create(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        "/users/new",
        data={
            "email": "x@example.com",
            "full_name": "X",
            "region": "NA",
            "is_admin": "1",
            "is_kt_contractor": "1",
        },
        follow_redirects=True,
    )
    assert b"Invalid role combination" in resp.data
    with app.app_context():
        assert db.session.query(User).filter_by(email="x@example.com").count() == 0


def test_contractor_cannot_be_combined_on_promote(app):
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
        data={
            "email": "p@example.com",
            "region": "NA",
            "is_admin": "1",
            "is_kt_contractor": "1",
        },
        follow_redirects=True,
    )
    assert b"Invalid role combination" in resp.data
    with app.app_context():
        assert db.session.query(User).filter_by(email="p@example.com").count() == 0


def test_staff_user_helper_true_for_non_contractor_roles(app):
    with app.app_context():
        admin = User(email="a@example.com", is_admin=True)
        contractor = User(email="c@example.com", is_kt_contractor=True)
        idle = User(email="i@example.com")
        db.session.add_all([admin, contractor, idle])
        db.session.commit()
        admin_db = db.session.get(User, admin.id)
        contractor_db = db.session.get(User, contractor.id)
        idle_db = db.session.get(User, idle.id)
        assert is_staff_user(admin_db)
        assert not is_staff_user(contractor_db)
        assert not is_staff_user(idle_db)


def test_nav_hides_user_admin_links_for_non_admin(app):
    with app.app_context():
        admin = User(email="a@example.com", is_admin=True)
        user = User(email="u@example.com")
        db.session.add_all([admin, user])
        db.session.commit()
        admin_db = db.session.get(User, admin.id)
        user_db = db.session.get(User, user.id)
        menu_admin = build_menu(admin_db, "ADMIN", True)
        menu_user = build_menu(user_db, "ADMIN", True)

        def ids(menu):
            out = []
            for item in menu:
                if item.get("id"):
                    out.append(item["id"])
                if item.get("children"):
                    out.extend(ids(item["children"]))
            return out

        assert "users" in ids(menu_admin)
        assert "users" not in ids(menu_user)

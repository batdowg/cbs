import os
import pytest

from app.app import create_app, db
from app.models import ProcessorAssignment, User

pytestmark = pytest.mark.smoke


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_processors_persist(app):
    with app.app_context():
        sys_admin = User(email="sys@example.com", is_app_admin=True, is_admin=True)
        sys_admin.set_password("x")
        admin_user = User(email="u1@example.com", is_admin=True)
        admin_user.set_password("x")
        db.session.add_all([sys_admin, admin_user])
        db.session.commit()
        admin_id = sys_admin.id
        u1_id = admin_user.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id
    resp = client.post(
        "/mail-settings/processors",
        data={"NA-Digital": [str(u1_id)]},
    )
    assert resp.status_code == 302
    with app.app_context():
        rows = ProcessorAssignment.query.all()
        assert len(rows) == 1
        assert rows[0].region == "NA"
        assert rows[0].processing_type == "Digital"
        assert rows[0].user_id == u1_id


def test_duplicate_assignments_deduped(app):
    with app.app_context():
        sys_admin = User(email="sys@example.com", is_app_admin=True, is_admin=True)
        sys_admin.set_password("x")
        admin_user = User(email="u1@example.com", is_admin=True)
        admin_user.set_password("x")
        db.session.add_all([sys_admin, admin_user])
        db.session.commit()
        admin_id = sys_admin.id
        u1_id = admin_user.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id
    resp = client.post(
        "/mail-settings/processors",
        data={"NA-Digital": [str(u1_id), str(u1_id)]},
    )
    assert resp.status_code == 302
    with app.app_context():
        rows = ProcessorAssignment.query.all()
        assert len(rows) == 1


def test_non_admin_rejected(app):
    with app.app_context():
        sys_admin = User(email="sys@example.com", is_app_admin=True, is_admin=True)
        sys_admin.set_password("x")
        admin_user = User(email="admin1@example.com", is_admin=True)
        admin_user.set_password("x")
        existing_non_admin = User(email="old@example.com")
        existing_non_admin.set_password("x")
        new_non_admin = User(email="new@example.com")
        new_non_admin.set_password("x")
        db.session.add_all(
            [sys_admin, admin_user, existing_non_admin, new_non_admin]
        )
        db.session.commit()
        db.session.add(
            ProcessorAssignment(
                region="NA", processing_type="Digital", user_id=existing_non_admin.id
            )
        )
        db.session.commit()
        admin_id = sys_admin.id
        admin_uid = admin_user.id
        existing_uid = existing_non_admin.id
        new_uid = new_non_admin.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id
    resp = client.post(
        "/mail-settings/processors",
        data={"NA-Digital": [str(existing_uid), str(admin_uid), str(new_uid)]},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Skipped non-administrator users" in resp.data
    with app.app_context():
        rows = ProcessorAssignment.query.filter_by(
            region="NA", processing_type="Digital"
        ).all()
        ids = {r.user_id for r in rows}
        assert existing_uid in ids
        assert admin_uid in ids
        assert new_uid not in ids

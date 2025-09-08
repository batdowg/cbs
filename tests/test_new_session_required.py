import os
import pytest

from app.app import create_app, db
from app.models import User, Client, WorkshopType, Session


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def _setup(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        client = Client(name="ClientA", status="active")
        db.session.add_all([admin, wt, client])
        db.session.commit()
        return admin.id, wt.id, client.id


def test_new_session_requires_fields(app):
    admin_id, wt_id, client_id = _setup(app)
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    # Missing title
    resp = client.post(
        "/sessions/new",
        data={
            "client_id": str(client_id),
            "region": "NA",
            "workshop_type_id": str(wt_id),
            "delivery_type": "Onsite",
            "workshop_language": "en",
            "capacity": "16",
            "start_date": "2100-01-01",
            "end_date": "2100-01-02",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/sessions/new")
    with app.app_context():
        assert Session.query.count() == 0

    # Valid submission
    resp = client.post(
        "/sessions/new",
        data={
            "title": "S1",
            "client_id": str(client_id),
            "region": "NA",
            "workshop_type_id": str(wt_id),
            "delivery_type": "Onsite",
            "workshop_language": "en",
            "capacity": "16",
            "start_date": "2100-01-01",
            "end_date": "2100-01-02",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/sessions/" in resp.headers["Location"]
    with app.app_context():
        assert Session.query.count() == 1


def test_new_session_form_shows_language_and_delivery(app):
    admin_id, _, _ = _setup(app)
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client.get("/sessions/new")
    assert resp.status_code == 200
    assert b"Delivery Type" in resp.data
    assert b"Workshop language" in resp.data
    assert b"<label>Language" not in resp.data

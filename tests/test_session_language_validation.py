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
        wt = WorkshopType(code="WT", name="WT", supported_languages=["en"], cert_series="fn")
        client = Client(name="ClientA", status="active")
        db.session.add_all([admin, wt, client])
        db.session.commit()
        return admin.id, wt.id, client.id


def test_language_mismatch_rejected(app):
    admin_id, wt_id, client_id = _setup(app)
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client.post(
        "/sessions/new",
        data={
            "title": "S1",
            "client_id": str(client_id),
            "region": "NA",
            "workshop_type_id": str(wt_id),
            "delivery_type": "Onsite",
            "workshop_language": "fr",
            "capacity": "16",
            "start_date": "2100-01-01",
            "end_date": "2100-01-02",
        },
    )
    assert resp.status_code == 400
    assert b"does not support" in resp.data
    with app.app_context():
        assert Session.query.count() == 0

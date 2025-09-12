import os

import pytest
from datetime import date

pytestmark = pytest.mark.smoke

from app.app import create_app, db
from app.models import User, WorkshopType, Session, Client


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


def setup_basic(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        client = Client(name="C1")
        db.session.add_all([admin, wt, client])
        db.session.commit()
        return admin.id, wt.id, client.id


def test_materials_only_creates_session(app):
    admin_id, wt_id, client_id = setup_basic(app)
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        "/sessions/new",
        data={
            "title": "MO",
            "client_id": str(client_id),
            "region": "NA",
            "workshop_language": "en",
            "action": "materials_only",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/materials")
    with app.app_context():
        sess = Session.query.filter_by(title="MO").first()
        assert sess and sess.materials_only
        assert sess.delivery_type == "Material Order"


def test_materials_only_session_detail_view(app):
    admin_id, wt_id, client_id = setup_basic(app)
    with app.app_context():
        sess = Session(
            title="MO",
            workshop_type_id=wt_id,
            client_id=client_id,
            materials_only=True,
            delivery_type="Material Order",
            start_date=date.today(),
            end_date=date.today(),
        )
        db.session.add(sess)
        db.session.commit()
        session_id = sess.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    assert b"Materials Order" in resp.data
    assert b"Participants" not in resp.data

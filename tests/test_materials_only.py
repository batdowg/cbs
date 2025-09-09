import os
from datetime import date

import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import User, WorkshopType, Session, SessionShipping, Client


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


def test_materials_only_creates_order_with_order_date(app):
    admin_id, wt_id, client_id = setup_basic(app)
    client = app.test_client()
    login(client, admin_id)
    today = date.today().isoformat()
    resp = client.post(
        "/materials-only",
        data={
            "title": "MO",
            "client_id": str(client_id),
            "region": "NA",
            "language": "en",
            "workshop_type_id": str(wt_id),
            "order_date": today,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        sess = Session.query.filter_by(title="MO").first()
        assert sess and sess.materials_only
        ship = SessionShipping.query.filter_by(session_id=sess.id).first()
        assert ship.order_date == date.fromisoformat(today)

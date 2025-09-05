import os
from datetime import date
import pytest

from app.app import create_app, db
from app.models import (
    User,
    WorkshopType,
    Session,
    MaterialType,
    Material,
    Client,
    ClientShippingLocation,
)


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_materials_page_loads(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", short_code="WT", name="WT")
        mt = MaterialType(name="Kit")
        client = Client(name="C1")
        ship = ClientShippingLocation(
            client=client,
            contact_name="CN",
            address_line1="A1",
            city="City",
            postal_code="123",
            country="US",
        )
        db.session.add_all([admin, wt, mt, client, ship])
        db.session.commit()
        mat = Material(material_type_id=mt.id, name="Sample Kit")
        sess = Session(
            title="S1",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            client=client,
            shipping_location=ship,
        )
        db.session.add_all([mat, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client.get(f"/sessions/{session_id}/materials")
    assert resp.status_code == 200
    assert b"Materials Order for" in resp.data


def test_materials_page_without_client(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", short_code="WT", name="WT")
        mt = MaterialType(name="Kit")
        mat = Material(material_type_id=mt.id, name="Sample Kit")
        sess = Session(
            title="S1",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
        )
        db.session.add_all([admin, wt, mt, mat, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client.get(f"/sessions/{session_id}/materials")
    assert resp.status_code == 200
    assert b"Materials Order for" in resp.data

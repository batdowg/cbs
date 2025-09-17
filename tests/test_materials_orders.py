import os
from datetime import date
import re

import pytest

import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import (
    User,
    WorkshopType,
    Session,
    SessionShipping,
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


def _setup_data():
    admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
    admin.set_password("x")
    wt = WorkshopType(code="WT", name="WT", cert_series="fn")
    mt = MaterialType(name="Kit")
    mat = Material(material_type_id=mt.id, name="Sample Kit")
    client = Client(name="C1")
    ship = ClientShippingLocation(
        client=client,
        contact_name="CN",
        address_line1="A1",
        city="City",
        postal_code="123",
        country="US",
    )
    sess = Session(
        title="S1",
        workshop_type=wt,
        start_date=date.today(),
        end_date=date.today(),
        client=client,
        shipping_location=ship,
    )
    db.session.add_all([admin, wt, mt, mat, client, ship, sess])
    db.session.commit()
    shipping = SessionShipping(session_id=sess.id, name="Main", order_date=date.today())
    db.session.add(shipping)
    db.session.commit()
    return admin.id, sess.id


def _setup_dashboard_sessions():
    admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
    admin.set_password("x")
    wt = WorkshopType(code="WT", name="WT", cert_series="fn")
    mt = MaterialType(name="Kit")
    mat = Material(material_type_id=mt.id, name="Sample Kit")
    client = Client(name="C1")
    ship = ClientShippingLocation(
        client=client,
        contact_name="CN",
        address_line1="A1",
        city="City",
        postal_code="123",
        country="US",
    )
    open_session = Session(
        title="Alpha Materials",
        workshop_type=wt,
        start_date=date.today(),
        end_date=date.today(),
        client=client,
        shipping_location=ship,
    )
    closed_session = Session(
        title="Closed Materials",
        workshop_type=wt,
        start_date=date.today(),
        end_date=date.today(),
        client=client,
        shipping_location=ship,
        status="Closed",
    )
    db.session.add_all(
        [admin, wt, mt, mat, client, ship, open_session, closed_session]
    )
    db.session.commit()
    open_shipping = SessionShipping(
        session_id=open_session.id,
        order_date=date.today(),
        order_type="KT-Run Standard materials",
    )
    closed_shipping = SessionShipping(
        session_id=closed_session.id,
        order_date=date.today(),
        order_type="KT-Run Standard materials",
    )
    db.session.add_all([open_shipping, closed_shipping])
    db.session.commit()
    return admin.id, open_session.title, closed_session.title


def _login(client, admin_id):
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id


def test_no_physical_components_box(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"Physical components" not in resp.data


def test_material_format_always_visible(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"Material format" in resp.data




def test_order_date_field_and_save(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"Order date" in resp.data
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={
            "action": "update_header",
            "materials_format": "ALL_DIGITAL",
            "order_date": "2025-01-02",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        assert shipment.order_date == date(2025, 1, 2)


def test_materials_dashboard_hides_closed_by_default(app):
    with app.app_context():
        admin_id, open_title, closed_title = _setup_dashboard_sessions()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get("/materials")
    assert resp.status_code == 200
    assert open_title.encode() in resp.data
    assert closed_title.encode() not in resp.data
    assert b"Status: not Closed" in resp.data
    assert b"Show closed sessions" in resp.data


def test_materials_dashboard_show_closed_filter(app):
    with app.app_context():
        admin_id, open_title, closed_title = _setup_dashboard_sessions()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get("/materials", query_string={"workshop_status": "all", "sort": "title"})
    assert resp.status_code == 200
    assert open_title.encode() in resp.data
    assert closed_title.encode() in resp.data
    assert b"Status: not Closed" not in resp.data
    assert b"Hide closed sessions" in resp.data
    assert b"workshop_status=not_closed" in resp.data


def test_materials_dashboard_hide_closed_filter(app):
    with app.app_context():
        admin_id, open_title, closed_title = _setup_dashboard_sessions()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get("/materials", query_string={"workshop_status": "not_closed"})
    assert resp.status_code == 200
    assert open_title.encode() in resp.data
    assert closed_title.encode() not in resp.data
    assert b"Status: not Closed" in resp.data
    assert b"Show closed sessions" in resp.data
    assert b"workshop_status=all" in resp.data

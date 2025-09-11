import os
from datetime import date
import re

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


def _login(client, admin_id):
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id


def test_always_renders_components_box(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"Physical components" in resp.data


def test_material_format_always_visible(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"Material format" in resp.data


def test_components_required_for_physical_and_mixed_only(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    _login(client, admin_id)
    # ALL_PHYSICAL requires components
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={"action": "update_header", "materials_format": "ALL_PHYSICAL"},
    )
    assert resp.status_code == 400
    # MIXED requires components
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={"action": "update_header", "materials_format": "MIXED"},
    )
    assert resp.status_code == 400
    # ALL_DIGITAL ignores components
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={"action": "update_header", "materials_format": "ALL_DIGITAL"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # SIM_ONLY ignores components
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={"action": "update_header", "materials_format": "SIM_ONLY"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_all_physical_prechecked_mixed_not_prechecked(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        shipment.materials_format = "ALL_PHYSICAL"
        shipment.materials_components = None
        db.session.commit()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/materials")
    # ALL_PHYSICAL pre-checks all boxes
    assert re.search(b'value="WORKSHOP_LEARNER"[^>]*checked', resp.data)
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        shipment.materials_format = "MIXED"
        shipment.materials_components = None
        db.session.commit()
    resp = client.get(f"/sessions/{session_id}/materials")
    assert not re.search(b'value="WORKSHOP_LEARNER"[^>]*checked', resp.data)


def test_all_physical_allows_partial_selection(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={
            "action": "update_header",
            "materials_format": "ALL_PHYSICAL",
            "components": ["WORKSHOP_LEARNER", "BOX_F"],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        assert shipment.materials_components == ["WORKSHOP_LEARNER", "BOX_F"]
    resp = client.get(f"/sessions/{session_id}/materials")
    assert re.search(b'value="WORKSHOP_LEARNER"[^>]*checked', resp.data)
    assert not re.search(b'value="SESSION_MATERIALS"[^>]*checked', resp.data)


def test_digital_and_sim_only_disable_components(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        shipment.materials_format = "ALL_DIGITAL"
        shipment.materials_components = ["WORKSHOP_LEARNER"]
        db.session.commit()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/materials")
    assert re.search(b'value="WORKSHOP_LEARNER"[^>]*disabled', resp.data)
    assert not re.search(b'value="WORKSHOP_LEARNER"[^>]*checked', resp.data)
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        shipment.materials_format = "SIM_ONLY"
        shipment.materials_components = ["WORKSHOP_LEARNER"]
        db.session.commit()
    resp = client.get(f"/sessions/{session_id}/materials")
    assert re.search(b'value="WORKSHOP_LEARNER"[^>]*disabled', resp.data)
    assert not re.search(b'value="WORKSHOP_LEARNER"[^>]*checked', resp.data)


def test_simulation_defaults_to_sim_only(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        shipment.order_type = "Simulation"
        shipment.materials_format = None
        db.session.commit()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/materials")
    assert re.search(b'<option value="SIM_ONLY"[^>]*selected', resp.data)


def test_sticky_values_on_error(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    _login(client, admin_id)
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={
            "action": "update_header",
            "materials_format": "ALL_PHYSICAL",
            "materials_po_number": "PO123",
            "arrival_date": "2024-01-01",
        },
    )
    assert resp.status_code == 400
    assert b"PO123" in resp.data
    assert b"2024-01-01" in resp.data
    assert b"Select physical components" in resp.data


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

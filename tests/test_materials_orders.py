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
    wt = WorkshopType(code="WT", name="WT")
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
    shipping = SessionShipping(session_id=sess.id, name="Main")
    db.session.add(shipping)
    db.session.commit()
    return admin.id, sess.id


def test_renders_components_for_physical_or_mixed_format(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        shipment.materials_format = "PHYSICAL"
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"name=\"components\"" in resp.data
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        shipment.materials_format = "MIXED"
        db.session.commit()
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"name=\"components\"" in resp.data
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        shipment.materials_format = "DIGITAL"
        shipment.materials_components = ["WORKSHOP_LEARNER"]
        db.session.commit()
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"name=\"components\"" not in resp.data


def test_requires_components_only_when_needed(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    # Missing components for physical format
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={
            "action": "update_header",
            "materials_format": "PHYSICAL",
        },
    )
    assert resp.status_code == 400
    assert b"Select physical components" in resp.data
    # Digital format doesn't require components
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={
            "action": "update_header",
            "materials_format": "DIGITAL",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # Physical with components succeeds
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={
            "action": "update_header",
            "materials_format": "PHYSICAL",
            "components": ["WORKSHOP_LEARNER", "BOX_F"],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        assert shipment.materials_components == ["WORKSHOP_LEARNER", "BOX_F"]


def test_post_preserves_user_input_on_error(app):
    with app.app_context():
        admin_id, session_id = _setup_data()
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={
            "action": "update_header",
            "materials_format": "PHYSICAL",
            "materials_po_number": "PO123",
            "arrival_date": "2024-01-01",
        },
    )
    assert resp.status_code == 400
    assert b"PO123" in resp.data
    assert b"2024-01-01" in resp.data
    assert b"Select physical components" in resp.data

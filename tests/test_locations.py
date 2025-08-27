import os
import sys
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import (
    Client,
    User,
    WorkshopType,
    Session,
    ClientWorkshopLocation,
    ClientShippingLocation,
    SessionShipping,
    ensure_virtual_workshop_locations,
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


def login_admin(client, admin_id):
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id


def test_virtual_defaults_idempotent(app):
    with app.app_context():
        c = Client(name="C1")
        db.session.add(c)
        db.session.commit()
        ensure_virtual_workshop_locations(c.id)
        ensure_virtual_workshop_locations(c.id)
        count = (
            db.session.query(ClientWorkshopLocation)
            .filter_by(client_id=c.id)
            .count()
        )
        assert count == 5


def test_session_form_filters_locations_and_inline(app):
    with app.app_context():
        admin = User(email="a@a", is_app_admin=True)
        admin.set_password("x")
        client = Client(name="C1")
        wl_active = ClientWorkshopLocation(client=client, label="L1", is_active=True)
        wl_inactive = ClientWorkshopLocation(client=client, label="L2", is_active=False)
        sl_active = ClientShippingLocation(
            client=client,
            contact_name="Ship1",
            address_line1="A1",
            city="City",
            postal_code="123",
            country="US",
            is_active=True,
        )
        sl_inactive = ClientShippingLocation(
            client=client,
            contact_name="Ship2",
            address_line1="A2",
            city="City",
            postal_code="123",
            country="US",
            is_active=False,
        )
        wt = WorkshopType(code="WT", name="WT")
        db.session.add_all([
            admin,
            client,
            wl_active,
            wl_inactive,
            sl_active,
            sl_inactive,
            wt,
        ])
        db.session.commit()
        admin_id = admin.id
        client_id = client.id
    tc = app.test_client()
    login_admin(tc, admin_id)
    resp = tc.get(f"/sessions/new?client_id={client_id}")
    assert b"L1" in resp.data
    assert b"L2" not in resp.data
    assert b"Ship1" in resp.data
    assert b"Ship2" not in resp.data
    resp = tc.post(
        f"/clients/{client_id}/workshop-locations/inline",
        data={"label": "New Virtual", "is_virtual": "1", "platform": "Zoom"},
    )
    assert b"selected" in resp.data


def test_materials_requires_shipping_location(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True)
        admin.set_password("x")
        client = Client(name="C1")
        wt = WorkshopType(code="WT", name="WT")
        sess = Session(title="S1", workshop_type=wt, client=client)
        db.session.add_all([admin, client, wt, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
        client_id = client.id
    tc = app.test_client()
    login_admin(tc, admin_id)
    resp = tc.get(f"/sessions/{session_id}/materials", follow_redirects=True)
    assert b"Shipping location required" in resp.data
    with app.app_context():
        ship = ClientShippingLocation(
            client_id=client_id,
            contact_name="CN",
            address_line1="A1",
            city="City",
            postal_code="123",
            country="US",
        )
        db.session.add(ship)
        db.session.commit()
        ship_id = ship.id
        sess = db.session.get(Session, session_id)
        sess.shipping_location_id = ship_id
        db.session.commit()
    resp = tc.post(
        f"/sessions/{session_id}/materials",
        data={"action": "update_header", "order_type": "Simulation"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).one()
        assert shipment.client_shipping_location_id == ship_id

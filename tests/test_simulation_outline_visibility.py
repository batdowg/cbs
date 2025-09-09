import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import (
    User,
    WorkshopType,
    Session,
    SessionShipping,
    SimulationOutline,
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


def _base_setup(sim_based=False):
    admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
    admin.set_password("x")
    wt = WorkshopType(code="WT", name="WT", simulation_based=sim_based, cert_series="fn")
    so = SimulationOutline(number="S1", skill="Custom", descriptor="Desc", level="Novice")
    client = Client(name="C1")
    ship = ClientShippingLocation(client=client, contact_name="CN", address_line1="A1", city="City", postal_code="123", country="US")
    sess = Session(
        title="S1",
        workshop_type=wt,
        start_date=date.today(),
        end_date=date.today(),
        client=client,
        shipping_location=ship,
    )
    db.session.add_all([admin, wt, so, client, ship, sess])
    db.session.commit()
    shipping = SessionShipping(session_id=sess.id, name="Main")
    db.session.add(shipping)
    db.session.commit()
    return admin.id, sess.id, so.id


def _login(client, admin_id):
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id


def test_outline_shown_when_workshop_type_simulation_based(app):
    with app.app_context():
        admin_id, session_id, _ = _base_setup(sim_based=True)
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/edit")
    assert b"Simulation Outline" in resp.data
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"Simulation Outline" in resp.data


def test_outline_hidden_when_not_simulation_based(app):
    with app.app_context():
        admin_id, session_id, _ = _base_setup(sim_based=False)
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}/edit")
    assert b"<label>Simulation Outline" not in resp.data
    resp = client.get(f"/sessions/{session_id}/materials")
    assert b"<label>Simulation Outline" not in resp.data


def test_outline_persists_when_saved_from_session_form(app):
    with app.app_context():
        admin_id, session_id, so_id = _base_setup(sim_based=True)
    client = app.test_client()
    _login(client, admin_id)
    resp = client.post(
        f"/sessions/{session_id}/edit",
        data={
            "title": "S1",
            "client_id": 1,
            "region": "NA",
            "workshop_type_id": 1,
            "delivery_type": "Onsite",
            "capacity": "10",
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
            "simulation_outline_id": so_id,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        sess = db.session.get(Session, session_id)
        assert sess.simulation_outline_id == so_id


def test_outline_updates_when_saved_from_materials_order(app):
    with app.app_context():
        admin_id, session_id, so_id = _base_setup(sim_based=True)
    client = app.test_client()
    _login(client, admin_id)
    resp = client.post(
        f"/sessions/{session_id}/materials",
        data={
            "action": "update_header",
            "simulation_outline_id": so_id,
            "materials_format": "ALL_DIGITAL",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        sess = db.session.get(Session, session_id)
        assert sess.simulation_outline_id == so_id


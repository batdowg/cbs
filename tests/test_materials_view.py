import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db  # noqa: E402
from app.models import (  # noqa: E402
    Client,
    ClientShippingLocation,
    Session,
    User,
    WorkshopType,
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


def test_materials_edit_shows_shipping_selector_for_finalized_session(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True)
        admin.set_password("secret")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="cert")
        client = Client(name="Client", status="active")
        location = ClientShippingLocation(
            client=client,
            title="HQ",
            contact_name="Alice",
            contact_email="alice@example.com",
            contact_phone="123-555-7890",
            address_line1="123 Main St",
            city="Townsville",
            state="TS",
            postal_code="90210",
            country="USA",
        )
        session = Session(
            title="Session",
            workshop_type=workshop_type,
            client=client,
            finalized=True,
        )
        db.session.add_all([admin, workshop_type, client, location, session])
        db.session.commit()
        session.shipping_location_id = location.id
        db.session.commit()
        admin_id = admin.id
        session_id = session.id

    client_tc = app.test_client()
    with client_tc.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id

    resp = client_tc.get(f"/sessions/{session_id}/materials")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'name="shipping_location_id"' in html
    assert 'id="add-shipping-location"' in html
    assert 'name="arrival_date"' in html

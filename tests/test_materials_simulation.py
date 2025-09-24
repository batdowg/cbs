from __future__ import annotations

from datetime import date

from app.app import db
from app.models import (
    Client,
    ClientShippingLocation,
    Language,
    MaterialOrderItem,
    MaterialsOption,
    Session,
    SessionShipping,
    SimulationOutline,
    User,
    WorkshopType,
    WorkshopTypeMaterialDefault,
)
from app.routes.materials import SIM_CREDITS_REF


def _seed_language():
    if not Language.query.filter_by(name="English").first():
        db.session.add(Language(name="English", sort_order=1))
        db.session.flush()


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _create_materials_session(
    *, simulation_based: bool = True, include_outline: bool = False
) -> dict[str, int | str]:
    _seed_language()
    admin = User(email="admin@example.com", is_admin=True, region="NA")
    admin.set_password("pw")
    client = Client(name="Client", status="active")
    code = "SIM" if simulation_based else "GEN"
    workshop_type = WorkshopType.query.filter_by(code=code).first()
    if not workshop_type:
        workshop_type = WorkshopType(
            code=code,
            name="Simulation Workshop" if simulation_based else "General Workshop",
            cert_series="fn",
            simulation_based=simulation_based,
        )
        db.session.add(workshop_type)
    outline_primary = SimulationOutline.query.filter_by(number="291104").first()
    if not outline_primary:
        outline_primary = SimulationOutline(
            number="291104",
            skill="Systematic Troubleshooting",
            descriptor="Primary",
            level="Novice",
        )
        db.session.add(outline_primary)
    outline_secondary = SimulationOutline.query.filter_by(number="291200").first()
    if not outline_secondary:
        outline_secondary = SimulationOutline(
            number="291200",
            skill="Systematic Troubleshooting",
            descriptor="Secondary",
            level="Novice",
        )
        db.session.add(outline_secondary)
    option = MaterialsOption.query.filter_by(
        order_type="KT-Run Standard materials", title="Digital Guide"
    ).first()
    if not option:
        option = MaterialsOption(
            order_type="KT-Run Standard materials",
            title="Digital Guide",
            formats=["Digital"],
        )
        db.session.add(option)
    db.session.add_all([admin, client])
    db.session.flush()
    default = WorkshopTypeMaterialDefault.query.filter_by(
        workshop_type_id=workshop_type.id,
        delivery_type="Virtual",
        region_code="NA",
        language="en",
        catalog_ref=f"materials_options:{option.id}",
    ).first()
    if not default:
        default = WorkshopTypeMaterialDefault(
            workshop_type_id=workshop_type.id,
            delivery_type="Virtual",
            region_code="NA",
            language="en",
            catalog_ref=f"materials_options:{option.id}",
            default_format="Digital",
            quantity_basis="Per learner",
        )
        db.session.add(default)
    session = Session(
        title="Sim Session",
        start_date=date.today(),
        end_date=date.today(),
        delivery_type="Virtual",
        region="NA",
        workshop_language="en",
        capacity=10,
        number_of_class_days=1,
        workshop_type=workshop_type,
        client=client,
    )
    if include_outline:
        session.simulation_outline = outline_primary
    db.session.add(session)
    db.session.flush()
    shipping = SessionShipping(
        session_id=session.id,
        created_by=admin.id,
        order_type="KT-Run Standard materials",
        material_sets=5,
        credits=2,
    )
    db.session.add(shipping)
    db.session.commit()
    return {
        "admin_id": admin.id,
        "session_id": session.id,
        "outline_primary_id": outline_primary.id,
        "outline_primary_number": outline_primary.number,
        "outline_secondary_id": outline_secondary.id,
        "outline_secondary_number": outline_secondary.number,
    }


def test_apply_defaults_requires_outline_for_simulation(app, client):
    with app.app_context():
        data = _create_materials_session(simulation_based=True, include_outline=False)
        session_id = data["session_id"]
        admin_id = data["admin_id"]
    _login(client, admin_id)
    response = client.post(
        f"/sessions/{session_id}/materials/apply-defaults",
        follow_redirects=False,
    )
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Select a Simulation Outline to continue." in html
    assert "Simulation Outline is required for simulation-based workshops." in html
    assert "Choose a <a href=\"#simulation-outline\">Simulation Outline</a> first." in html
    assert "field-error" in html
    with app.app_context():
        assert (
            MaterialOrderItem.query.filter_by(session_id=session_id).count() == 0
        )


def test_materials_save_requires_outline_for_simulation(app, client):
    with app.app_context():
        data = _create_materials_session(simulation_based=True, include_outline=False)
        session_id = data["session_id"]
        admin_id = data["admin_id"]
    _login(client, admin_id)
    response = client.post(
        f"/sessions/{session_id}/materials",
        data={
            "action": "update_header",
            "order_type": "KT-Run Standard materials",
            "material_sets": "5",
            "credits": "2",
        },
    )
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Select a Simulation Outline to continue." in html
    assert "Simulation Outline is required for simulation-based workshops." in html
    with app.app_context():
        shipping = SessionShipping.query.filter_by(session_id=session_id).one()
        assert shipping.credits == 2
        assert (
            MaterialOrderItem.query.filter_by(session_id=session_id).count() == 0
        )


def test_apply_defaults_syncs_sim_credits(app, client):
    with app.app_context():
        data = _create_materials_session(simulation_based=True, include_outline=True)
        session_id = data["session_id"]
        admin_id = data["admin_id"]
        outline_primary_number = data["outline_primary_number"]
        outline_secondary_id = data["outline_secondary_id"]
        outline_secondary_number = data["outline_secondary_number"]
    _login(client, admin_id)
    first = client.post(
        f"/sessions/{session_id}/materials/apply-defaults",
        follow_redirects=False,
    )
    assert first.status_code == 302
    with app.app_context():
        items = MaterialOrderItem.query.filter_by(session_id=session_id).all()
        sim_items = [i for i in items if i.catalog_ref == SIM_CREDITS_REF]
        assert len(sim_items) == 1
        sim_item = sim_items[0]
        assert sim_item.title_snapshot == f"SIM Credits ({outline_primary_number})"
        assert sim_item.language == "en"
        assert sim_item.format == "Digital"
        assert sim_item.quantity == 2
    again = client.post(
        f"/sessions/{session_id}/materials/apply-defaults",
        follow_redirects=False,
    )
    assert again.status_code == 302
    with app.app_context():
        count = (
            MaterialOrderItem.query.filter_by(
                session_id=session_id, catalog_ref=SIM_CREDITS_REF
            ).count()
        )
        assert count == 1
        shipment = SessionShipping.query.filter_by(session_id=session_id).one()
        shipment.credits = 4
        session = db.session.get(Session, session_id)
        session.simulation_outline_id = outline_secondary_id
        db.session.commit()
    updated = client.post(
        f"/sessions/{session_id}/materials/apply-defaults",
        follow_redirects=False,
    )
    assert updated.status_code == 302
    with app.app_context():
        sim_item = (
            MaterialOrderItem.query.filter_by(
                session_id=session_id, catalog_ref=SIM_CREDITS_REF
            )
            .order_by(MaterialOrderItem.id)
            .one()
        )
        assert sim_item.title_snapshot == f"SIM Credits ({outline_secondary_number})"
        assert sim_item.quantity == 4
        shipment = SessionShipping.query.filter_by(session_id=session_id).one()
        shipment.credits = 0
        db.session.commit()
    cleared = client.post(
        f"/sessions/{session_id}/materials/apply-defaults",
        follow_redirects=False,
    )
    assert cleared.status_code == 302
    with app.app_context():
        assert (
            MaterialOrderItem.query.filter_by(
                session_id=session_id, catalog_ref=SIM_CREDITS_REF
            ).count()
            == 0
        )


def test_apply_defaults_skips_sim_credits_for_non_simulation(app, client):
    with app.app_context():
        data = _create_materials_session(simulation_based=False, include_outline=False)
        session_id = data["session_id"]
        admin_id = data["admin_id"]
    _login(client, admin_id)
    response = client.post(
        f"/sessions/{session_id}/materials/apply-defaults",
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert (
            MaterialOrderItem.query.filter_by(
                session_id=session_id, catalog_ref=SIM_CREDITS_REF
            ).count()
            == 0
        )


def test_apply_defaults_preserves_shipping_fields(app, client):
    with app.app_context():
        data = _create_materials_session(simulation_based=False, include_outline=False)
        session_id = data["session_id"]
        admin_id = data["admin_id"]
        shipment = SessionShipping.query.filter_by(session_id=session_id).one()
        sess = db.session.get(Session, session_id)
        location = ClientShippingLocation(
            client_id=sess.client_id,
            title="HQ",
            contact_name="Ship Contact",
            contact_email="ship@example.com",
            contact_phone="555-0100",
            address_line1="123 Ship St",
            city="Ship City",
            state="ST",
            postal_code="12345",
            country="USA",
        )
        db.session.add(location)
        db.session.flush()
        shipment.client_shipping_location_id = location.id
        shipment.contact_name = "Ship Name"
        shipment.contact_email = "ship@example.com"
        shipment.contact_phone = "555-0100"
        shipment.address_line1 = "123 Ship St"
        shipment.address_line2 = "Suite 5"
        shipment.city = "Ship City"
        shipment.state = "ST"
        shipment.postal_code = "12345"
        shipment.country = "USA"
        shipment.courier = "CourierX"
        shipment.tracking = "TRACK123"
        shipment.ship_date = date(2024, 1, 2)
        expected = {
            "client_shipping_location_id": location.id,
            "contact_name": shipment.contact_name,
            "contact_email": shipment.contact_email,
            "contact_phone": shipment.contact_phone,
            "address_line1": shipment.address_line1,
            "address_line2": shipment.address_line2,
            "city": shipment.city,
            "state": shipment.state,
            "postal_code": shipment.postal_code,
            "country": shipment.country,
            "courier": shipment.courier,
            "tracking": shipment.tracking,
            "ship_date": shipment.ship_date,
        }
        db.session.commit()
    _login(client, admin_id)
    response = client.post(
        f"/sessions/{session_id}/materials/apply-defaults",
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).one()
        for field, value in expected.items():
            assert getattr(shipment, field) == value

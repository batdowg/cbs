from datetime import date

from app.app import db
from app.models import Client, Session, SessionShipping, User, WorkshopType
from app.shared.sessions_lifecycle import enforce_material_only_rules


def test_dashboards_respect_material_filters(app, client):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True, region="NA")
        admin.set_password("pw")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        client_record = Client(name="Client")
        workshop_session = Session(
            title="Workshop Only",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            delivery_type="In person",
            workshop_type=workshop_type,
            client=client_record,
            lead_facilitator=admin,
            no_material_order=True,
        )
        materials_session = Session(
            title="Materials Only",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            delivery_type="Material only",
            workshop_type=workshop_type,
            client=client_record,
            lead_facilitator=admin,
            materials_only=True,
        )
        db.session.add_all([admin, workshop_type, client_record, workshop_session, materials_session])
        db.session.flush()
        materials_session.ready_for_delivery = True
        enforce_material_only_rules(materials_session)
        db.session.add_all(
            [
                SessionShipping(
                    session_id=workshop_session.id,
                    order_type=None,
                    material_sets=0,
                ),
                SessionShipping(
                    session_id=materials_session.id,
                    order_type="KT-Run Standard materials",
                    material_sets=10,
                ),
            ]
        )
        db.session.commit()
        admin_id = admin.id
        workshop_id = workshop_session.id
        materials_id = materials_session.id

    with client.session_transaction() as sess:
        sess["user_id"] = admin_id

    home = client.get("/home", follow_redirects=True)
    html = home.get_data(as_text=True)
    assert "Workshop Only" in html
    assert "Materials Only" not in html

    materials = client.get("/materials", follow_redirects=True)
    table = materials.get_data(as_text=True)
    assert "Workshop Only" not in table

    # Verify routes remain reachable for original sessions
    detail = client.get(f"/sessions/{workshop_id}")
    assert detail.status_code == 200
    material_detail = client.get(f"/sessions/{materials_id}/materials")
    assert material_detail.status_code == 200

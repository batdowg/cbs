from datetime import date

from app.app import db
from app.models import (
    Client,
    Language,
    Session,
    SessionShipping,
    User,
    WorkshopType,
)


def _seed_language():
    if not Language.query.filter_by(name="English").first():
        db.session.add(Language(name="English", sort_order=1))
        db.session.flush()


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_new_materials_order_lists_only_active_clients(app, client):
    with app.app_context():
        _seed_language()
        admin = User(email="admin@example.com", is_admin=True, region="NA")
        admin.set_password("pw")
        active_client = Client(name="Active Client", status="active")
        inactive_client = Client(name="Inactive Client", status="inactive")
        db.session.add_all([admin, active_client, inactive_client])
        db.session.commit()
        admin_id = admin.id

    _login(client, admin_id)

    response = client.get("/sessions/new")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active Client" in html
    assert "Inactive Client" not in html


def test_edit_session_preserves_inactive_client(app, client):
    with app.app_context():
        _seed_language()
        admin = User(email="admin@example.com", is_admin=True, region="NA")
        admin.set_password("pw")
        inactive_client = Client(name="Inactive Co", status="inactive")
        other_inactive = Client(name="Dormant Co", status="inactive")
        active_client = Client(name="Active Co", status="active")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        db.session.add_all(
            [
                admin,
                inactive_client,
                other_inactive,
                active_client,
                workshop_type,
            ]
        )
        db.session.flush()
        materials_session = Session(
            title="Materials Only Session",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            delivery_type="Material only",
            materials_only=True,
            client_id=inactive_client.id,
            workshop_type=workshop_type,
            capacity=10,
        )
        db.session.add(materials_session)
        db.session.flush()
        db.session.add(
            SessionShipping(session_id=materials_session.id, created_by=admin.id)
        )
        db.session.commit()
        admin_id = admin.id
        session_id = materials_session.id
        inactive_id = inactive_client.id
        other_inactive_id = other_inactive.id
        workshop_type_id = workshop_type.id

    _login(client, admin_id)

    edit_page = client.get(f"/sessions/{session_id}/edit")
    assert edit_page.status_code == 200
    html = edit_page.get_data(as_text=True)
    assert f'value="{inactive_id}" selected' in html
    assert f'value="{other_inactive_id}"' not in html

    form_data = {
        "title": "Materials Only Session",
        "start_date": date.today().isoformat(),
        "end_date": date.today().isoformat(),
        "delivery_type": "Material only",
        "region": "NA",
        "workshop_language": "en",
        "capacity": "10",
        "number_of_class_days": "1",
        "client_id": str(inactive_id),
        "workshop_type_id": str(workshop_type_id),
    }
    save_response = client.post(
        f"/sessions/{session_id}/edit",
        data=form_data,
        follow_redirects=False,
    )
    assert save_response.status_code == 302


def test_materials_order_create_rejects_inactive_client(app, client):
    with app.app_context():
        _seed_language()
        admin = User(email="admin@example.com", is_admin=True, region="NA")
        admin.set_password("pw")
        inactive_client = Client(name="Inactive Client", status="inactive")
        db.session.add_all([admin, inactive_client])
        db.session.commit()
        admin_id = admin.id
        inactive_id = inactive_client.id

    _login(client, admin_id)

    response = client.post(
        "/sessions/new",
        data={
            "action": "materials_only",
            "title": "New Materials Order",
            "client_id": str(inactive_id),
            "region": "NA",
            "workshop_language": "en",
        },
    )
    assert response.status_code == 400
    assert response.get_data(as_text=True) == "Client is inactive."

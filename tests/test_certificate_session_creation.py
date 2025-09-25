from datetime import date, time

from app.app import db
from app.models import (
    Client,
    ClientWorkshopLocation,
    Language,
    Session,
    User,
    WorkshopType,
)


def _seed_language():
    if not Language.query.filter_by(name="English").first():
        db.session.add(Language(name="English", sort_order=1, is_active=True))
        db.session.flush()


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_certificate_session_form_creates_session(app, client):
    with app.app_context():
        _seed_language()
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("pw")
        facilitator = User(email="facilitator@example.com", is_kt_delivery=True)
        facilitator.set_password("pw")
        workshop_type = WorkshopType(
            code="WT1",
            name="Certificate Workshop",
            cert_series="fn",
            active=True,
        )
        client_record = Client(name="Client", status="active")
        location = ClientWorkshopLocation(client=client_record, label="Main Hall")
        db.session.add_all(
            [admin, facilitator, workshop_type, client_record, location]
        )
        db.session.commit()
        admin_id = admin.id
        facilitator_id = facilitator.id
        client_id = client_record.id
        workshop_type_id = workshop_type.id
        location_id = location.id

    _login(client, admin_id)

    payload = {
        "client_id": str(client_id),
        "region": "NA",
        "workshop_type_id": str(workshop_type_id),
        "workshop_language": "en",
        "workshop_location_id": str(location_id),
        "start_date": date.today().isoformat(),
        "end_date": date.today().isoformat(),
        "daily_start_time": "09:00",
        "daily_end_time": "16:00",
        "number_of_class_days": "1",
        "lead_facilitator_id": str(facilitator_id),
    }

    response = client.post("/certificates/new", data=payload, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        created = Session.query.filter_by(client_id=client_id).one()
        assert response.headers["Location"].endswith(f"/sessions/{created.id}")
        assert created.is_certificate_only is True
        assert created.ready_for_delivery is True
        assert created.ready_at is not None
        assert created.delivery_type == "Certificate only"
        assert created.no_material_order is True
        assert created.materials_ordered is False
        assert created.no_prework is True
        assert created.prework_disabled is True
        assert created.lead_facilitator_id == facilitator_id
        assert created.workshop_type_id == workshop_type_id
        assert created.client_id == client_id
        assert created.workshop_location_id == location_id
        assert created.region == "NA"
        assert created.workshop_language == "en"
        assert created.start_date == date.today()
        assert created.end_date == date.today()
        assert created.daily_start_time == time(9, 0)
        assert created.daily_end_time == time(16, 0)
        assert created.number_of_class_days == 1


def test_certificates_new_route_unique(app):
    with app.app_context():
        rules = [rule for rule in app.url_map.iter_rules() if rule.rule == "/certificates/new"]
        assert len(rules) == 1
        rule = rules[0]
        assert rule.endpoint == "certificates.new_certificate_session"
        assert {"GET", "POST"}.issubset(rule.methods)

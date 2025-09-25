from datetime import date

from app.app import db
from app.models import (
    Client,
    Language,
    MaterialOrderItem,
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


def _base_form_payload(session: Session) -> dict[str, str]:
    return {
        "title": session.title,
        "client_id": str(session.client_id),
        "region": session.region,
        "workshop_type_id": str(session.workshop_type_id or ""),
        "delivery_type": session.delivery_type or "",
        "workshop_language": session.workshop_language,
        "capacity": str(session.capacity or 10),
        "number_of_class_days": str(session.number_of_class_days or 1),
        "start_date": session.start_date.isoformat() if session.start_date else date.today().isoformat(),
        "end_date": session.end_date.isoformat() if session.end_date else date.today().isoformat(),
        "daily_start_time": "08:00",
        "daily_end_time": "17:00",
        "timezone": session.timezone or "UTC",
    }


def test_certificate_only_session_autoready_on_create(app, client):
    with app.app_context():
        _seed_language()
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("pw")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        client_record = Client(name="Client", status="active")
        db.session.add_all([admin, workshop_type, client_record])
        db.session.commit()
        admin_id = admin.id
        wt_id = workshop_type.id
        client_id = client_record.id

    _login(client, admin_id)

    payload = {
        "title": "Certificate Session",
        "client_id": str(client_id),
        "region": "NA",
        "workshop_type_id": str(wt_id),
        "delivery_type": "Certificate only",
        "workshop_language": "en",
        "capacity": "15",
        "number_of_class_days": "1",
        "start_date": date.today().isoformat(),
        "end_date": date.today().isoformat(),
        "daily_start_time": "09:00",
        "daily_end_time": "17:00",
        "timezone": "UTC",
    }

    response = client.post("/sessions/new", data=payload, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        created = Session.query.filter_by(title="Certificate Session").one()
        assert created.ready_for_delivery is True
        assert created.materials_ordered is False
        assert created.is_certificate_only is True


def test_certificate_only_edit_sets_ready(app, client):
    with app.app_context():
        _seed_language()
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("pw")
        workshop_type = WorkshopType(code="WT2", name="Workshop 2", cert_series="fn")
        client_record = Client(name="Client", status="active")
        session = Session(
            title="Editable Session",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            capacity=12,
            delivery_type="Onsite",
            ready_for_delivery=False,
        )
        session.client = client_record
        session.workshop_type = workshop_type
        db.session.add_all([admin, workshop_type, client_record, session])
        db.session.commit()
        admin_id = admin.id
        session_id = session.id

    _login(client, admin_id)

    with app.app_context():
        sess = db.session.get(Session, session_id)
        payload = _base_form_payload(sess)
        payload.update({
            "delivery_type": "Certificate only",
            "workshop_type_id": str(sess.workshop_type_id),
            "client_id": str(sess.client_id),
        })

    response = client.post(
        f"/sessions/{session_id}/edit",
        data=payload,
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        refreshed = db.session.get(Session, session_id)
        assert refreshed.ready_for_delivery is True
        assert refreshed.materials_ordered is False
        assert refreshed.is_certificate_only is True


def test_certificate_only_blocks_materials_and_prework_routes(app, client):
    with app.app_context():
        _seed_language()
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("pw")
        workshop_type = WorkshopType(code="WT3", name="Workshop 3", cert_series="fn")
        client_record = Client(name="Client", status="active")
        session = Session(
            title="Blocked Session",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            capacity=10,
            delivery_type="Certificate only",
            ready_for_delivery=True,
            is_certificate_only=True,
        )
        session.client = client_record
        session.workshop_type = workshop_type
        db.session.add_all([admin, workshop_type, client_record, session])
        db.session.commit()
        admin_id = admin.id
        session_id = session.id

    _login(client, admin_id)

    prework = client.get(
        f"/sessions/{session_id}/prework", follow_redirects=False
    )
    assert prework.status_code == 302
    assert prework.headers["Location"].endswith(f"/sessions/{session_id}")

    materials = client.get(
        f"/sessions/{session_id}/materials", follow_redirects=False
    )
    assert materials.status_code == 404


def test_materials_dashboard_excludes_certificate_only(app, client):
    with app.app_context():
        _seed_language()
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("pw")
        wt = WorkshopType(code="WT4", name="Workshop 4", cert_series="fn")
        client_record = Client(name="Client", status="active")
        cert_session = Session(
            title="Cert Materials",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            capacity=8,
            delivery_type="Certificate only",
            ready_for_delivery=True,
            is_certificate_only=True,
        )
        cert_session.client = client_record
        cert_session.workshop_type = wt
        other_session = Session(
            title="Regular Materials",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            capacity=8,
            delivery_type="Onsite",
        )
        other_session.client = client_record
        other_session.workshop_type = wt
        db.session.add_all([admin, wt, client_record, cert_session, other_session])
        db.session.flush()
        db.session.add_all(
            [
                SessionShipping(
                    session_id=cert_session.id,
                    order_type="KT-Run Standard materials",
                ),
                SessionShipping(
                    session_id=other_session.id,
                    order_type="KT-Run Standard materials",
                ),
                MaterialOrderItem(
                    session_id=other_session.id,
                    catalog_ref="manual:1",
                    title_snapshot="Kit",
                    quantity=1,
                    language="en",
                    format="Digital",
                    processed=True,
                ),
            ]
        )
        db.session.commit()
        admin_id = admin.id
        cert_id = cert_session.id
        other_id = other_session.id

    _login(client, admin_id)

    resp = client.get("/materials")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Regular Materials" in html
    assert "Cert Materials" not in html

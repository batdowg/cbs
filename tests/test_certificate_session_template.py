from datetime import date

from app.app import db
from app.models import Client, Language, Session, User, WorkshopType


def _seed_language():
    if not Language.query.filter_by(name="English").first():
        db.session.add(Language(name="English", sort_order=1, is_active=True))
        db.session.flush()


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_certificate_detail_hides_materials_and_prework(app, client):
    with app.app_context():
        _seed_language()
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("pw")
        workshop_type = WorkshopType(code="WTX", name="Workshop", cert_series="fn", active=True)
        client_record = Client(name="Client", status="active")
        session = Session(
            title="Certificate Detail",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            ready_for_delivery=True,
            delivery_type="Certificate only",
            is_certificate_only=True,
        )
        session.client = client_record
        session.workshop_type = workshop_type
        db.session.add_all([admin, workshop_type, client_record, session])
        db.session.commit()
        admin_id = admin.id
        session_id = session.id

    _login(client, admin_id)

    response = client.get(f"/sessions/{session_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Certificate-only session" in html
    assert f"/sessions/{session_id}/prework" not in html
    assert f"/sessions/{session_id}/materials" not in html
    assert "Participants" in html

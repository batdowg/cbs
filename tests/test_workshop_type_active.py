import pytest
from datetime import date, time

from app.app import db
from app.models import (
    CertificateTemplateSeries,
    Client,
    Session,
    User,
    WorkshopType,
)


ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "pw"
SERIES_CODE = "fn"


def _setup_admin(app):
    with app.app_context():
        admin = User(
            email=ADMIN_EMAIL,
            is_app_admin=True,
            is_admin=True,
            region="NA",
        )
        admin.set_password(ADMIN_PASSWORD)
        series = CertificateTemplateSeries(
            code=SERIES_CODE,
            name="Foundational",
            is_active=True,
        )
        db.session.add_all([admin, series])
        db.session.commit()


def _login(client):
    return client.post(
        "/login",
        data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        follow_redirects=True,
    )


@pytest.mark.no_smoke
def test_workshop_type_inactive_checkbox_persists(app, client):
    _setup_admin(app)
    _login(client)

    with client.session_transaction() as session:
        session["_csrf_token"] = "token"

    response = client.post(
        "/workshop-types/new",
        data={
            "csrf_token": "token",
            "code": "INACT",
            "name": "Inactive Type",
            "cert_series": SERIES_CODE,
            "supported_languages": ["en"],
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Inactive" in page

    with app.app_context():
        wt = WorkshopType.query.filter_by(code="INACT").one()
        assert wt.active is False
        wt_id = wt.id

    edit_page = client.get(f"/workshop-types/{wt_id}/edit")
    assert edit_page.status_code == 200
    edit_html = edit_page.get_data(as_text=True)
    checkbox_line = next(
        line
        for line in edit_html.splitlines()
        if 'name="active"' in line and 'value="1"' in line
    )
    assert "checked" not in checkbox_line


@pytest.mark.no_smoke
def test_new_session_excludes_inactive_workshop_types(app, client):
    _setup_admin(app)
    with app.app_context():
        active_type = WorkshopType(
            code="ACTIVE",
            name="Active Type",
            cert_series=SERIES_CODE,
            active=True,
        )
        inactive_type = WorkshopType(
            code="INACTIVE",
            name="Inactive Type",
            cert_series=SERIES_CODE,
            active=False,
        )
        db.session.add_all([active_type, inactive_type])
        db.session.commit()
        active_id = active_type.id
        inactive_id = inactive_type.id

    _login(client)
    response = client.get("/sessions/new")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f'value="{active_id}"' in html
    assert f'value="{inactive_id}"' not in html


@pytest.mark.no_smoke
def test_edit_session_preserves_inactive_type(app, client):
    _setup_admin(app)
    with app.app_context():
        inactive_type = WorkshopType(
            code="LEGACY",
            name="Legacy Type",
            cert_series=SERIES_CODE,
            active=False,
        )
        client_record = Client(name="ClientCo")
        today = date.today()
        session = Session(
            title="Legacy Session",
            start_date=today,
            end_date=today,
            daily_start_time=time.fromisoformat("08:00"),
            daily_end_time=time.fromisoformat("17:00"),
            timezone="UTC",
            delivery_type="Virtual",
            region="NA",
            workshop_language="en",
            capacity=10,
            number_of_class_days=1,
            workshop_type=inactive_type,
            client=client_record,
        )
        db.session.add_all([inactive_type, client_record, session])
        db.session.commit()
        session_id = session.id
        workshop_type_id = inactive_type.id
        client_id = client_record.id

    _login(client)
    form_page = client.get(f"/sessions/{session_id}/edit")
    assert form_page.status_code == 200
    form_html = form_page.get_data(as_text=True)
    assert f'value="{workshop_type_id}"' in form_html

    today_str = date.today().isoformat()
    response = client.post(
        f"/sessions/{session_id}/edit",
        data={
            "title": "Legacy Session",
            "start_date": today_str,
            "end_date": today_str,
            "daily_start_time": "08:00",
            "daily_end_time": "17:00",
            "timezone": "UTC",
            "delivery_type": "Virtual",
            "region": "NA",
            "workshop_language": "en",
            "capacity": "10",
            "number_of_class_days": "1",
            "workshop_type_id": str(workshop_type_id),
            "client_id": str(client_id),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        refreshed = db.session.get(Session, session_id)
        assert refreshed.workshop_type_id == workshop_type_id

from datetime import date, datetime, time

from app.app import db
from app.models import Client, Language, Session, User


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _ensure_language() -> None:
    if not Language.query.filter_by(name="English").first():
        db.session.add(Language(name="English", sort_order=1, is_active=True))
        db.session.flush()


def _create_certificate_manager(email: str = "cert@example.com") -> User:
    user = User(email=email, is_certificate_manager=True)
    db.session.add(user)
    db.session.flush()
    return user


def _create_sessions(client_record: Client) -> tuple[Session, Session]:
    cert_session = Session(
        title="Certificate Cohort",
        client_id=client_record.id,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 12),
        daily_start_time=time(9, 0),
        daily_end_time=time(11, 0),
        delivery_type="Certificate only",
        region="NA",
        workshop_language="en",
        is_certificate_only=True,
        ready_for_delivery=True,
        delivered=True,
        delivered_at=datetime(2024, 1, 12, 17, 0),
        no_material_order=True,
        no_prework=True,
        prework_disabled=True,
    )
    regular_session = Session(
        title="Regular Workshop",
        client_id=client_record.id,
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 2),
        daily_start_time=time(9, 0),
        daily_end_time=time(12, 0),
        delivery_type="Virtual",
        region="NA",
        workshop_language="en",
    )
    db.session.add_all([cert_session, regular_session])
    db.session.flush()
    return cert_session, regular_session


def test_certificate_manager_home_and_navigation(app, client):
    with app.app_context():
        _ensure_language()
        cert_user = _create_certificate_manager()
        client_record = Client(name="Acme Corp", status="active")
        db.session.add(client_record)
        db.session.flush()
        cert_session, regular_session = _create_sessions(client_record)
        db.session.commit()
        user_id = cert_user.id
        cert_title = cert_session.title
        regular_title = regular_session.title

    _login(client, user_id)
    response = client.get("/home", follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == "/my-sessions"
    html = response.get_data(as_text=True)
    assert cert_title in html
    assert regular_title not in html
    assert "New Certificate Session" in html
    assert "New Order" not in html
    assert "Workshop Dashboard" not in html
    assert "kt-sidebar-footer" not in html


def test_certificate_manager_route_guards(app, client):
    with app.app_context():
        _ensure_language()
        cert_user = _create_certificate_manager("role-check@example.com")
        client_record = Client(name="Globex", status="active")
        db.session.add(client_record)
        db.session.flush()
        cert_session, _ = _create_sessions(client_record)
        db.session.commit()
        user_id = cert_user.id
        session_id = cert_session.id

    _login(client, user_id)

    resp = client.get("/certificate-sessions/new")
    assert resp.status_code == 200

    resp = client.get("/sessions")
    assert resp.status_code == 403

    resp = client.get("/materials")
    assert resp.status_code == 403

    resp = client.get("/clients/")
    assert resp.status_code == 200

    resp = client.get("/settings/languages/")
    assert resp.status_code == 403

    resp = client.post(f"/sessions/{session_id}/generate")
    assert resp.status_code in {302, 303}

    resp = client.get("/workshops/1")
    assert resp.status_code == 403

import os
import os
from datetime import date, timedelta

import pytest

from app.app import create_app, db
from app.models import User, WorkshopType, Session, SimulationOutline, Client, SessionShipping
from app.shared.materials import latest_arrival_date


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def setup_basic(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", simulation_based=True, cert_series="fn")
        client = Client(name="C1")
        sim = SimulationOutline(number="123456", skill="Risk", descriptor="Desc", level="Novice")
        db.session.add_all([admin, wt, client, sim])
        db.session.commit()
        return admin.id, wt.id, client.id, sim.id


def test_simulation_outline_dropdown_and_save(app):
    admin_id, wt_id, client_id, sim_id = setup_basic(app)
    client = app.test_client()
    login(client, admin_id)
    future_start = date.today() + timedelta(days=30)
    future_end = future_start + timedelta(days=1)
    data = {
        "title": "S1",
        "client_id": str(client_id),
        "region": "NA",
        "workshop_type_id": str(wt_id),
        "delivery_type": "Onsite",
        "workshop_language": "en",
        "capacity": "10",
        "start_date": future_start.isoformat(),
        "end_date": future_end.isoformat(),
        "simulation_outline_id": str(sim_id),
        "timezone": "UTC",
        "daily_start_time": "08:00",
        "daily_end_time": "17:00",
    }
    resp = client.post("/sessions/new", data=data)
    assert resp.status_code == 302
    with app.app_context():
        sess = Session.query.filter_by(title="S1").first()
        assert sess.simulation_outline_id == sim_id


def test_latest_arrival_date_helper(app):
    admin_id, wt_id, client_id, sim_id = setup_basic(app)
    with app.app_context():
        sess = Session(
            title="S2",
            workshop_type_id=wt_id,
            client_id=client_id,
            start_date=date.today(),
            end_date=date.today(),
        )
        db.session.add(sess)
        db.session.commit()
        ship = SessionShipping(session_id=sess.id, arrival_date=date(2025, 1, 2))
        db.session.add(ship)
        db.session.commit()
        assert latest_arrival_date(sess) == date(2025, 1, 2)


def test_materials_list_shows_latest_arrival(app):
    admin_id, wt_id, client_id, sim_id = setup_basic(app)
    with app.app_context():
        sess = Session(
            title="S3",
            workshop_type_id=wt_id,
            client_id=client_id,
            start_date=date.today(),
            end_date=date.today(),
        )
        db.session.add(sess)
        db.session.commit()
        ship = SessionShipping(session_id=sess.id, arrival_date=date(2025, 1, 5))
        db.session.add(ship)
        db.session.commit()
        session_id = sess.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.get("/materials")
    assert b"Latest Arrival Date" in resp.data
    assert b"2025-01-05" in resp.data

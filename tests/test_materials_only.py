import os

from datetime import date

import pytest

pytestmark = pytest.mark.smoke

from app.app import create_app, db
from app.models import (
    Client,
    Participant,
    Session,
    SessionParticipant,
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


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def setup_basic(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        client = Client(name="C1")
        db.session.add_all([admin, wt, client])
        db.session.commit()
        return admin.id, wt.id, client.id


def create_material_only_session(
    app,
    wt_id: int,
    client_id: int,
    *,
    facilitator_id: int | None = None,
    with_participant: bool = False,
    title: str = "MO",
) -> int:
    with app.app_context():
        facilitator: User | None = None
        if facilitator_id is not None:
            facilitator = db.session.get(User, facilitator_id)
        sess = Session(
            title=title,
            workshop_type_id=wt_id,
            client_id=client_id,
            materials_only=True,
            delivery_type="Material only",
            start_date=date.today(),
            end_date=date.today(),
            region="NA",
            workshop_language="en",
            capacity=10,
        )
        if facilitator:
            sess.lead_facilitator_id = facilitator.id
            sess.facilitators = [facilitator]
        db.session.add(sess)
        db.session.flush()
        if with_participant:
            participant = Participant(email=f"p{sess.id}@example.com")
            db.session.add(participant)
            db.session.flush()
            db.session.add(
                SessionParticipant(
                    session_id=sess.id, participant_id=participant.id
                )
            )
        db.session.commit()
        return sess.id


def test_materials_only_creates_session(app):
    admin_id, wt_id, client_id = setup_basic(app)
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        "/sessions/new",
        data={
            "title": "MO",
            "client_id": str(client_id),
            "region": "NA",
            "workshop_language": "en",
            "action": "materials_only",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/materials")
    with app.app_context():
        sess = Session.query.filter_by(title="MO").first()
        assert sess and sess.materials_only
        assert sess.delivery_type == "Material only"


def test_materials_only_session_detail_view(app):
    admin_id, wt_id, client_id = setup_basic(app)
    session_id = create_material_only_session(app, wt_id, client_id)
    client = app.test_client()
    login(client, admin_id)
    resp = client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    assert b"Materials Order" in resp.data
    assert b"Participants" not in resp.data


def test_material_only_ready_sets_closed(app):
    admin_id, wt_id, client_id = setup_basic(app)
    session_id = create_material_only_session(
        app, wt_id, client_id, with_participant=True, title="MO Ready"
    )
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        f"/sessions/{session_id}/edit",
        data={
            "title": "MO Ready",
            "client_id": str(client_id),
            "region": "NA",
            "workshop_language": "en",
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
            "capacity": "10",
            "delivery_type": "Material only",
            "workshop_type_id": str(wt_id),
            "ready_for_delivery": "1",
            "daily_start_time": "08:00",
            "daily_end_time": "17:00",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        sess = db.session.get(Session, session_id)
        assert sess.status == "Closed"
        assert sess.ready_for_delivery is True
        assert sess.delivered is False


def test_material_only_finalize_sets_closed(app):
    admin_id, wt_id, client_id = setup_basic(app)
    session_id = create_material_only_session(
        app, wt_id, client_id, with_participant=True, title="MO Final"
    )
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(
        f"/sessions/{session_id}/edit",
        data={
            "title": "MO Final",
            "client_id": str(client_id),
            "region": "NA",
            "workshop_language": "en",
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
            "capacity": "10",
            "delivery_type": "Material only",
            "workshop_type_id": str(wt_id),
            "finalized": "1",
            "daily_start_time": "08:00",
            "daily_end_time": "17:00",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        sess = db.session.get(Session, session_id)
        assert sess.status == "Closed"
        assert sess.finalized is True
        assert sess.delivered is False


def test_workshop_view_redirects_for_material_only(app):
    admin_id, wt_id, client_id = setup_basic(app)
    with app.app_context():
        facilitator = User(email="fac@example.com", is_kt_delivery=True)
        facilitator.set_password("x")
        db.session.add(facilitator)
        db.session.commit()
        facilitator_id = facilitator.id
    session_id = create_material_only_session(
        app,
        wt_id,
        client_id,
        facilitator_id=facilitator_id,
        title="MO Guard",
    )
    client = app.test_client()
    login(client, facilitator_id)
    resp = client.get(f"/workshops/{session_id}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/sessions/{session_id}")


def test_my_sessions_links_material_only_to_session_detail(app):
    admin_id, wt_id, client_id = setup_basic(app)
    with app.app_context():
        facilitator = User(email="fac2@example.com", is_kt_delivery=True)
        facilitator.set_password("x")
        db.session.add(facilitator)
        db.session.commit()
        facilitator_id = facilitator.id
    session_id = create_material_only_session(
        app,
        wt_id,
        client_id,
        facilitator_id=facilitator_id,
        title="MO My Sessions",
    )
    client = app.test_client()
    login(client, facilitator_id)
    resp = client.get("/my-sessions")
    assert resp.status_code == 200
    assert f"/sessions/{session_id}".encode() in resp.data
    assert f"/workshops/{session_id}".encode() not in resp.data

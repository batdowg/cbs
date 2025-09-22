import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import (
    Client,
    Participant,
    ParticipantAccount,
    ParticipantAttendance,
    Session,
    SessionParticipant,
    User,
    WorkshopType,
)


pytestmark = pytest.mark.smoke


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    application = create_app()
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()


def login_user(client, *, user_id=None, participant_account_id=None):
    with client.session_transaction() as sess:
        sess.clear()
        if user_id is not None:
            sess["user_id"] = user_id
        if participant_account_id is not None:
            sess["participant_account_id"] = participant_account_id


def seed_session(app, *, materials_only: bool = False):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("x")
        facilitator = User(email="fac@example.com", is_kt_delivery=True)
        facilitator.set_password("x")
        other_facilitator = User(email="other@example.com", is_kt_delivery=True)
        other_facilitator.set_password("x")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="SER")
        client = Client(name="Client")
        db.session.add_all([admin, facilitator, other_facilitator, workshop_type, client])
        db.session.flush()

        session = Session(
            title="Session",
            client_id=client.id,
            workshop_type_id=workshop_type.id,
            start_date=date.today(),
            end_date=date.today(),
            region="NA",
            workshop_language="en",
            capacity=25,
            delivery_type="Material only" if materials_only else "In Person",
            materials_only=materials_only,
            number_of_class_days=3,
        )
        if not materials_only:
            session.lead_facilitator_id = facilitator.id
            session.facilitators = [facilitator]
        db.session.add(session)
        db.session.flush()

        participants = []
        for idx in range(2):
            participant = Participant(email=f"p{idx}@example.com")
            db.session.add(participant)
            db.session.flush()
            db.session.add(
                SessionParticipant(
                    session_id=session.id, participant_id=participant.id
                )
            )
            participants.append(participant.id)
        db.session.commit()
        return {
            "admin_id": admin.id,
            "facilitator_id": facilitator.id,
            "other_facilitator_id": other_facilitator.id,
            "session_id": session.id,
            "participant_ids": participants,
        }


def test_toggle_attendance_creates_and_updates(app):
    seed = seed_session(app)
    client = app.test_client()
    login_user(client, user_id=seed["admin_id"])

    session_id = seed["session_id"]
    participant_id = seed["participant_ids"][0]

    resp = client.post(
        f"/sessions/{session_id}/attendance/toggle",
        json={
            "participant_id": participant_id,
            "day_index": 1,
            "attended": True,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["attended"] is True

    resp = client.post(
        f"/sessions/{session_id}/attendance/toggle",
        json={
            "participant_id": participant_id,
            "day_index": 1,
            "attended": False,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["attended"] is False

    with app.app_context():
        record = ParticipantAttendance.query.filter_by(
            session_id=session_id, participant_id=participant_id, day_index=1
        ).one()
        assert record.attended is False


def test_mark_all_attended_sets_all_days(app):
    seed = seed_session(app)
    client = app.test_client()
    login_user(client, user_id=seed["admin_id"])

    session_id = seed["session_id"]
    first_participant = seed["participant_ids"][0]
    with app.app_context():
        db.session.add(
            ParticipantAttendance(
                session_id=session_id,
                participant_id=first_participant,
                day_index=1,
                attended=False,
            )
        )
        db.session.commit()

    resp = client.post(f"/sessions/{session_id}/attendance/mark_all_attended")
    assert resp.status_code == 200
    assert resp.get_json()["updated_count"] == 6

    with app.app_context():
        records = ParticipantAttendance.query.filter_by(session_id=session_id).all()
        assert len(records) == 6
        assert all(record.attended is True for record in records)


def test_toggle_rejects_invalid_day_index(app):
    seed = seed_session(app)
    client = app.test_client()
    login_user(client, user_id=seed["admin_id"])

    session_id = seed["session_id"]
    participant_id = seed["participant_ids"][0]

    resp = client.post(
        f"/sessions/{session_id}/attendance/toggle",
        json={
            "participant_id": participant_id,
            "day_index": 4,
            "attended": True,
        },
    )
    assert resp.status_code == 400


def test_toggle_rejects_participant_not_in_session(app):
    seed = seed_session(app)
    client = app.test_client()
    login_user(client, user_id=seed["admin_id"])

    session_id = seed["session_id"]
    with app.app_context():
        outsider = Participant(email="outsider@example.com")
        db.session.add(outsider)
        db.session.commit()
        outsider_id = outsider.id

    resp = client.post(
        f"/sessions/{session_id}/attendance/toggle",
        json={
            "participant_id": outsider_id,
            "day_index": 1,
            "attended": True,
        },
    )
    assert resp.status_code == 400


def test_material_only_session_blocked(app):
    seed = seed_session(app, materials_only=True)
    client = app.test_client()
    login_user(client, user_id=seed["admin_id"])

    session_id = seed["session_id"]
    participant_id = seed["participant_ids"][0]

    resp = client.post(
        f"/sessions/{session_id}/attendance/toggle",
        json={
            "participant_id": participant_id,
            "day_index": 1,
            "attended": True,
        },
    )
    assert resp.status_code == 403

    resp = client.post(f"/sessions/{session_id}/attendance/mark_all_attended")
    assert resp.status_code == 403


def test_csa_blocked_from_attendance(app):
    seed = seed_session(app)
    client = app.test_client()

    with app.app_context():
        account = ParticipantAccount(email="csa@example.com", full_name="CSA")
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    login_user(client, participant_account_id=account_id)
    session_id = seed["session_id"]
    participant_id = seed["participant_ids"][0]
    resp = client.post(
        f"/sessions/{session_id}/attendance/toggle",
        json={
            "participant_id": participant_id,
            "day_index": 1,
            "attended": True,
        },
    )
    assert resp.status_code == 403


def test_unassigned_facilitator_blocked(app):
    seed = seed_session(app)
    client = app.test_client()
    login_user(client, user_id=seed["other_facilitator_id"])

    session_id = seed["session_id"]
    participant_id = seed["participant_ids"][0]
    resp = client.post(
        f"/sessions/{session_id}/attendance/toggle",
        json={
            "participant_id": participant_id,
            "day_index": 1,
            "attended": True,
        },
    )
    assert resp.status_code == 403

from datetime import date

import pytest

from app.app import db
from app.models import Client, Participant, Session, SessionParticipant, User, WorkshopType


@pytest.fixture
def session_with_clients(app):
    with app.app_context():
        client_primary = Client(name="Alpha Corp")
        client_alt = Client(name="Beta LLC")
        workshop_type = WorkshopType(name="Test", code="TST", cert_series="GEN")
        db.session.add_all([client_primary, client_alt, workshop_type])
        db.session.flush()
        sess = Session(
            title="Client Session",
            workshop_type_id=workshop_type.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            workshop_language="en",
            client_id=client_primary.id,
            number_of_class_days=0,
        )
        db.session.add(sess)
        admin = User(email="admin@example.com", is_admin=True)
        contractor = User(email="contractor@example.com", is_kt_contractor=True)
        db.session.add_all([admin, contractor])
        db.session.commit()
        yield {
            "session_id": sess.id,
            "primary_client_id": client_primary.id,
            "alt_client_id": client_alt.id,
            "admin_id": admin.id,
            "contractor_id": contractor.id,
        }


def test_add_participant_defaults_to_session_client(client, app, session_with_clients):
    sess_info = session_with_clients
    with client.session_transaction() as flask_session:
        flask_session["user_id"] = sess_info["admin_id"]

    resp = client.post(
        f"/sessions/{sess_info['session_id']}/participants/add",
        data={
            "first_name": "Alex",
            "last_name": "Smith",
            "email": "alex@example.com",
            "title": "Manager",
        },
    )
    assert resp.status_code == 302

    with app.app_context():
        link = SessionParticipant.query.join(Participant).filter(
            SessionParticipant.session_id == sess_info["session_id"],
            Participant.email == "alex@example.com",
        ).one()
        assert link.company_client_id == sess_info["primary_client_id"]


def test_add_participant_allows_staff_override(client, app, session_with_clients):
    sess_info = session_with_clients
    with client.session_transaction() as flask_session:
        flask_session["user_id"] = sess_info["admin_id"]

    resp = client.post(
        f"/sessions/{sess_info['session_id']}/participants/add",
        data={
            "first_name": "Jamie",
            "last_name": "Lee",
            "email": "jamie@example.com",
            "title": "Director",
            "company_client_id": str(sess_info["alt_client_id"]),
        },
    )
    assert resp.status_code == 302

    with app.app_context():
        link = SessionParticipant.query.join(Participant).filter(
            SessionParticipant.session_id == sess_info["session_id"],
            Participant.email == "jamie@example.com",
        ).one()
        assert link.company_client_id == sess_info["alt_client_id"]


def test_contractor_cannot_override_company(client, app, session_with_clients):
    sess_info = session_with_clients
    with client.session_transaction() as flask_session:
        flask_session["user_id"] = sess_info["contractor_id"]

    resp = client.post(
        f"/sessions/{sess_info['session_id']}/participants/add",
        data={
            "first_name": "Riley",
            "last_name": "Jordan",
            "email": "riley@example.com",
            "title": "Associate",
            "company_client_id": str(sess_info["alt_client_id"]),
        },
    )
    assert resp.status_code == 302

    with app.app_context():
        link = SessionParticipant.query.join(Participant).filter(
            SessionParticipant.session_id == sess_info["session_id"],
            Participant.email == "riley@example.com",
        ).one()
        assert link.company_client_id == sess_info["primary_client_id"]


def test_generate_single_updates_company_for_staff(client, app, session_with_clients):
    sess_info = session_with_clients
    with app.app_context():
        participant = Participant(
            email="update@example.com",
            first_name="Taylor",
            last_name="Green",
        )
        db.session.add(participant)
        db.session.flush()
        link = SessionParticipant(
            session_id=sess_info["session_id"],
            participant_id=participant.id,
            completion_date=date(2024, 1, 2),
            company_client_id=sess_info["primary_client_id"],
        )
        db.session.add(link)
        db.session.commit()
        assert link.id is not None
        participant_id = participant.id

    with client.session_transaction() as flask_session:
        flask_session["user_id"] = sess_info["admin_id"]

    resp = client.post(
        f"/sessions/{sess_info['session_id']}/participants/{participant_id}/generate",
        data={
            "action": "save",
            "company_client_id": str(sess_info["alt_client_id"]),
        },
    )
    assert resp.status_code == 302

    with app.app_context():
        from app.shared.acl import is_kt_staff

        admin = db.session.get(User, sess_info["admin_id"])
        assert is_kt_staff(admin)
        assert Client.query.get(sess_info["alt_client_id"]) is not None
        assert db.session.get(Client, sess_info["alt_client_id"]) is not None
        raw_value = db.session.execute(
            db.text(
                "SELECT company_client_id FROM session_participants WHERE session_id = :sid AND participant_id = :pid"
            ),
            {"sid": sess_info["session_id"], "pid": participant_id},
        ).scalar_one()
        link = SessionParticipant.query.filter_by(
            session_id=sess_info["session_id"],
            participant_id=participant_id,
        ).one()
        assert raw_value == sess_info["alt_client_id"]
        assert link.company_client_id == sess_info["alt_client_id"]

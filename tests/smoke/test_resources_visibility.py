from datetime import date

from app.app import db
from app.models import (
    Participant,
    ParticipantAccount,
    Resource,
    Session,
    SessionParticipant,
    User,
    WorkshopType,
)


def test_resources_visibility_and_collapsed_panels(app, client):
    with app.app_context():
        facilitator = User(email="facilitator@example.com", is_kt_delivery=True)
        facilitator.set_password("pw")
        account = ParticipantAccount(email="participant@example.com", full_name="Learner")
        account.set_password("pw")
        participant = Participant(
            email="participant@example.com", full_name="Learner", account=account
        )
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        session = Session(
            title="Resources",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            workshop_type=workshop_type,
            lead_facilitator=facilitator,
        )
        facilitator_resource = Resource(
            name="Facilitator Playbook",
            type="LINK",
            resource_value="https://example.com/facilitator",
            audience="Facilitator",
            language="en",
            workshop_types=[workshop_type],
        )
        participant_resource = Resource(
            name="Participant Guide",
            type="LINK",
            resource_value="https://example.com/participant",
            audience="Participant",
            language="en",
            workshop_types=[workshop_type],
        )
        db.session.add_all(
            [
                facilitator,
                account,
                participant,
                workshop_type,
                session,
                facilitator_resource,
                participant_resource,
            ]
        )
        db.session.flush()
        db.session.add(SessionParticipant(session_id=session.id, participant_id=participant.id))
        db.session.commit()
        facilitator_id = facilitator.id
        session_id = session.id
        participant_account_id = account.id

    # Facilitator view shows facilitator resources collapsed by default
    with client.session_transaction() as sess:
        sess["user_id"] = facilitator_id
    workshop_view = client.get(f"/workshops/{session_id}")
    workshop_html = workshop_view.get_data(as_text=True)
    assert "Facilitator Playbook" in workshop_html
    assert "<details class=\"resource-item\">" in workshop_html
    assert "resource-item\" open" not in workshop_html

    # Participant view shows participant resources and hides facilitator-only items
    client.get("/logout")
    with client.session_transaction() as sess:
        sess["participant_account_id"] = participant_account_id
    resources = client.get("/my-resources")
    resources_html = resources.get_data(as_text=True)
    assert "Participant Guide" in resources_html
    assert "Facilitator Playbook" not in resources_html

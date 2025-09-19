from datetime import date, time

from app.app import create_app, db
from app.models import (
    User,
    WorkshopType,
    PreworkTemplate,
    PreworkQuestion,
    Session,
    ParticipantAccount,
    Participant,
    SessionParticipant,
    PreworkAssignment,
    PreworkAnswer,
)


def _setup_base_data():
    app = create_app()
    with app.app_context():
        db.create_all()
        admin = User(email="admin@example.com", is_app_admin=True)
        facilitator = User(email="fac@example.com", is_kt_delivery=True)
        wt = WorkshopType(code="PWX", name="Prework X", cert_series="fn")
        template = PreworkTemplate(workshop_type=wt, info_html="info")
        q1 = PreworkQuestion(template=template, position=1, text="Question A", kind="TEXT")
        q2 = PreworkQuestion(template=template, position=2, text="Question B", kind="LIST")
        session = Session(
            title="Session",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            daily_start_time=time(9, 0),
            daily_end_time=time(17, 0),
            workshop_language="en",
        )
        session.lead_facilitator = facilitator
        account_one = ParticipantAccount(
            email="jane@example.com", full_name="Jane Doe"
        )
        account_two = ParticipantAccount(
            email="john@example.com", full_name="John Smith"
        )
        participant_one = Participant(
            email="jane@example.com", full_name="Jane Doe", account=account_one
        )
        participant_two = Participant(
            email="john@example.com", full_name="John Smith", account=account_two
        )
        db.session.add_all(
            [
                admin,
                facilitator,
                wt,
                template,
                q1,
                q2,
                session,
                account_one,
                account_two,
                participant_one,
                participant_two,
            ]
        )
        db.session.flush()
        db.session.add_all(
            [
                SessionParticipant(
                    session_id=session.id, participant_id=participant_one.id
                ),
                SessionParticipant(
                    session_id=session.id, participant_id=participant_two.id
                ),
            ]
        )
        snapshot = {
            "questions": [
                {"index": 1, "text": "Question A", "required": True, "kind": "TEXT"},
                {"index": 2, "text": "Question B", "required": True, "kind": "LIST"},
            ],
            "resources": [],
        }
        assignment_one = PreworkAssignment(
            session_id=session.id,
            participant_account_id=account_one.id,
            template_id=template.id,
            status="COMPLETED",
            snapshot_json=snapshot,
        )
        assignment_two = PreworkAssignment(
            session_id=session.id,
            participant_account_id=account_two.id,
            template_id=template.id,
            status="COMPLETED",
            snapshot_json=snapshot,
        )
        db.session.add_all([assignment_one, assignment_two])
        db.session.flush()
        db.session.add_all(
            [
                PreworkAnswer(
                    assignment_id=assignment_one.id,
                    question_index=1,
                    item_index=0,
                    answer_text="Yes",
                ),
                PreworkAnswer(
                    assignment_id=assignment_one.id,
                    question_index=1,
                    item_index=1,
                    answer_text="needs\nlaptop",
                ),
                PreworkAnswer(
                    assignment_id=assignment_one.id,
                    question_index=2,
                    item_index=0,
                    answer_text="3 years",
                ),
                PreworkAnswer(
                    assignment_id=assignment_one.id,
                    question_index=2,
                    item_index=1,
                    answer_text="hardware",
                ),
                PreworkAnswer(
                    assignment_id=assignment_two.id,
                    question_index=1,
                    item_index=0,
                    answer_text="No",
                ),
            ]
        )
        db.session.commit()
        return (
            app,
            session.id,
            admin.id,
            facilitator.id,
        )


def test_prework_summary_shared_between_views():
    app, session_id, admin_id, facilitator_id = _setup_base_data()

    with app.test_client() as client:
        with client.session_transaction() as session_store:
            session_store["user_id"] = facilitator_id
        workshop_resp = client.get(f"/workshops/{session_id}")
        assert workshop_resp.status_code == 200
        workshop_html = workshop_resp.data.decode()
        assert "Prework summary" in workshop_html
        assert "<h3 class=\"kt-card-title\">Question A</h3>" in workshop_html
        assert "<li><strong>Jane Doe</strong>; Yes; needs laptop</li>" in workshop_html
        assert "<li><strong>John Smith</strong>; No</li>" in workshop_html
        assert "<h3 class=\"kt-card-title\">Question B</h3>" in workshop_html
        assert "<li><strong>Jane Doe</strong>; 3 years; hardware</li>" in workshop_html

        with client.session_transaction() as session_store:
            session_store["user_id"] = admin_id
        staff_resp = client.get(f"/sessions/{session_id}/prework")
        assert staff_resp.status_code == 200
        staff_html = staff_resp.data.decode()
        for snippet in [
            "<h3 class=\"kt-card-title\">Question A</h3>",
            "<li><strong>Jane Doe</strong>; Yes; needs laptop</li>",
            "<li><strong>John Smith</strong>; No</li>",
            "<h3 class=\"kt-card-title\">Question B</h3>",
            "<li><strong>Jane Doe</strong>; 3 years; hardware</li>",
        ]:
            assert snippet in staff_html


def test_prework_summary_empty_state():
    app = create_app()
    with app.app_context():
        db.create_all()
        admin = User(email="staff@example.com", is_app_admin=True)
        facilitator = User(email="runner@example.com", is_kt_delivery=True)
        wt = WorkshopType(code="PWE", name="Prework Empty", cert_series="fn")
        session = Session(
            title="Empty",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            daily_start_time=time(9, 0),
            daily_end_time=time(17, 0),
            workshop_language="en",
        )
        session.lead_facilitator = facilitator
        db.session.add_all([admin, facilitator, wt, session])
        db.session.commit()
        session_id = session.id
        admin_id = admin.id
        facilitator_id = facilitator.id

    with app.test_client() as client:
        with client.session_transaction() as session_store:
            session_store["user_id"] = facilitator_id
        workshop_resp = client.get(f"/workshops/{session_id}")
        assert workshop_resp.status_code == 200
        assert b"No prework submitted yet." in workshop_resp.data

        with client.session_transaction() as session_store:
            session_store["user_id"] = admin_id
        staff_resp = client.get(f"/sessions/{session_id}/prework")
        assert staff_resp.status_code == 200
        assert b"No prework submitted yet." in staff_resp.data

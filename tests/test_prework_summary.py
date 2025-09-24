from app.app import db
from app.models import (
    ParticipantAccount,
    PreworkAnswer,
    PreworkAssignment,
    PreworkQuestion,
    PreworkTemplate,
    Session,
    WorkshopType,
)
from app.shared.prework_summary import get_session_prework_summary


def _build_prework_summary(app, question_text: str, *, answer_text: str = "Answer"):
    with app.app_context():
        workshop_type = WorkshopType(
            code="WT1",
            name="Workshop",
            cert_series="std",
        )
        db.session.add(workshop_type)
        db.session.flush()

        session = Session(
            title="Test Session",
            workshop_type_id=workshop_type.id,
            workshop_language="en",
        )
        db.session.add(session)
        db.session.flush()

        template = PreworkTemplate(
            workshop_type_id=workshop_type.id,
            language="en",
            is_active=True,
            require_completion=True,
        )
        db.session.add(template)
        db.session.flush()

        question = PreworkQuestion(
            template_id=template.id,
            position=1,
            text=question_text,
            required=True,
            kind="TEXT",
        )
        db.session.add(question)
        db.session.flush()

        account = ParticipantAccount(
            email="alice@example.com",
            full_name="Alice Example",
        )
        db.session.add(account)
        db.session.flush()

        assignment = PreworkAssignment(
            session_id=session.id,
            participant_account_id=account.id,
            template_id=template.id,
            snapshot_json={
                "questions": [
                    {
                        "index": 1,
                        "text": question_text,
                        "required": True,
                        "kind": "TEXT",
                        "min_items": None,
                        "max_items": None,
                    }
                ]
            },
        )
        db.session.add(assignment)
        db.session.flush()

        answer = PreworkAnswer(
            assignment_id=assignment.id,
            question_index=1,
            item_index=0,
            answer_text=answer_text,
        )
        db.session.add(answer)

        db.session.commit()

        return get_session_prework_summary(session.id)


def test_prework_summary_uses_first_line_of_multiparagraph_question(app):
    question_text = "<p>What are your goals?</p><p>Share details for the facilitator.</p>"
    summary = _build_prework_summary(app, question_text)

    assert summary[0]["question_headline"] == "What are your goals?"
    assert summary[0]["responses"][0]["answer_text"] == "Answer"


def test_prework_summary_strips_html_formatting_for_headline(app):
    question_text = "<p><strong>Describe your plan</strong><br>Include <em>details</em> in full.</p>"
    summary = _build_prework_summary(app, question_text)

    assert summary[0]["question_headline"] == "Describe your plan"
    assert summary[0]["responses"][0]["name"] == "Alice Example"


def test_prework_summary_handles_single_line_question(app):
    question_text = "Share one word to describe today."
    summary = _build_prework_summary(app, question_text)

    assert summary[0]["question_headline"] == "Share one word to describe today."
    assert summary[0]["responses"][0]["answer_text"] == "Answer"

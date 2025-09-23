from datetime import date

import pytest

from app.app import db
from app.models import (
    CertificateTemplate,
    CertificateTemplateSeries,
    Language,
    Participant,
    ParticipantAccount,
    Session,
    SessionParticipant,
    User,
    WorkshopType,
)
from app.services.attendance import mark_all_attended, upsert_attendance
from app.shared.certificates import CertificateAttendanceError, render_certificate


@pytest.fixture(autouse=True)
def _seed_language(app):
    with app.app_context():
        if not Language.query.filter_by(name="English").first():
            db.session.add(Language(name="English"))
            db.session.commit()


def test_attendance_enables_certificates(app):
    with app.app_context():
        series = CertificateTemplateSeries(code="SER", name="Series")
        template_a4 = CertificateTemplate(
            series=series,
            language="en",
            size="A4",
            filename="fncert_template_a4_en.pdf",
        )
        template_letter = CertificateTemplate(
            series=series,
            language="en",
            size="LETTER",
            filename="fncert_template_letter_en.pdf",
        )
        facilitator = User(email="facilitator@example.com", is_admin=True, region="NA")
        facilitator.set_password("pw")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="SER")
        session = Session(
            title="Attendance",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=2,
            workshop_type=workshop_type,
            lead_facilitator=facilitator,
        )
        account = ParticipantAccount(email="participant@example.com", full_name="Learner")
        account.set_password("pw")
        participant = Participant(
            email="participant@example.com",
            full_name="Learner",
            account=account,
        )
        db.session.add_all(
            [
                series,
                template_a4,
                template_letter,
                facilitator,
                workshop_type,
                session,
                account,
                participant,
            ]
        )
        db.session.flush()
        db.session.add(SessionParticipant(session_id=session.id, participant_id=participant.id))
        db.session.commit()
        session_id = session.id
        participant_id = participant.id
        account_id = account.id

    with app.app_context():
        session = db.session.get(Session, session_id)
        # Mark only day one attended
        upsert_attendance(session, participant_id, 1, True)
        db.session.commit()
        account = db.session.get(ParticipantAccount, account_id)
        with pytest.raises(CertificateAttendanceError):
            render_certificate(session, account)

    with app.app_context():
        session = db.session.get(Session, session_id)
        total = mark_all_attended(session)
        assert total == 2
        db.session.commit()
        account = db.session.get(ParticipantAccount, account_id)
        path = render_certificate(session, account)
        assert path.endswith(".pdf")

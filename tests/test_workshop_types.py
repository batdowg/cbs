import os
import sys
from datetime import date

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import (
    WorkshopType,
    Session,
    Participant,
    SessionParticipant,
    Certificate,
)
from app.utils.certificates import generate_for_session


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_workshop_type_code_unique(app):
    with app.app_context():
        wt1 = WorkshopType(code="abc", name="One")
        db.session.add(wt1)
        db.session.commit()
        wt2 = WorkshopType(code="aBc", name="Two")
        db.session.add(wt2)
        with pytest.raises(Exception):
            db.session.commit()


def test_session_sets_code_from_workshop_type(app):
    with app.app_context():
        wt = WorkshopType(code="AAA", name="Type A")
        sess = Session(title="S1")
        sess.workshop_type = wt
        db.session.add_all([wt, sess])
        db.session.commit()
        assert sess.code == "AAA"


def test_certificate_uses_workshop_type_name(app):
    with app.app_context():
        wt = WorkshopType(code="BBB", name="Type B")
        sess = Session(title="S2", workshop_type=wt, end_date=date.today())
        p = Participant(email="p@example.com", full_name="P")
        db.session.add_all([wt, sess, p])
        db.session.flush()
        link = SessionParticipant(
            session_id=sess.id, participant_id=p.id, completion_date=date.today()
        )
        db.session.add(link)
        db.session.commit()
        generate_for_session(sess.id)
        cert = db.session.query(Certificate).one()
        assert cert.workshop_name == wt.name

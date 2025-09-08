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
    ParticipantAccount,
    SessionParticipant,
    Certificate,
    CertificateTemplateSeries,
    CertificateTemplate,
)
from app.utils.certificates import render_for_session


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
        wt1 = WorkshopType(code="abc", name="One", cert_series="fn")
        db.session.add(wt1)
        db.session.commit()
        wt2 = WorkshopType(code="aBc", name="Two", cert_series="fn")
        db.session.add(wt2)
        with pytest.raises(Exception):
            db.session.commit()


def test_session_sets_code_from_workshop_type(app):
    with app.app_context():
        wt = WorkshopType(code="AAA", name="Type A", cert_series="fn")
        sess = Session(title="S1")
        sess.workshop_type = wt
        db.session.add_all([wt, sess])
        db.session.commit()
        assert sess.code == "AAA"


def test_certificate_uses_workshop_type_name(app):
    with app.app_context():
        series = CertificateTemplateSeries(code="fn", name="Default")
        tmpl = CertificateTemplate(series=series, language="es", size="A4", filename="fncert_template_a4_es.pdf")
        wt = WorkshopType(code="BBB", name="Type B", cert_series="fn")
        sess = Session(title="S2", workshop_type=wt, end_date=date.today(), workshop_language="es")
        acc = ParticipantAccount(email="p@example.com", full_name="P")
        p = Participant(email="p@example.com", full_name="P", account=acc)
        db.session.add_all([series, tmpl, wt, sess, acc, p])
        db.session.flush()
        link = SessionParticipant(
            session_id=sess.id, participant_id=p.id, completion_date=date.today()
        )
        db.session.add(link)
        db.session.commit()
        render_for_session(sess.id)
        cert = db.session.query(Certificate).one()
        assert cert.workshop_name == wt.name

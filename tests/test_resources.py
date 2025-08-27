import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import (
    WorkshopType,
    Session,
    Participant,
    SessionParticipant,
    ParticipantAccount,
    Resource,
)
from app.forms.resource_forms import slugify_filename


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv/resources", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_resource_validation_and_slug(app):
    with app.app_context():
        r = Resource(name="Link", type="LINK", resource_value="https://example.com")
        r.validate()
        r2 = Resource(name="Doc", type="DOCUMENT", resource_value="")
        with pytest.raises(ValueError):
            r2.validate()
        fname = slugify_filename("DA Template", "My File.XLSX")
        assert fname == "da-template.xlsx"


def test_my_resources_view(app):
    with app.app_context():
        wt = WorkshopType(code="ABC", name="Type A")
        sess = Session(title="S1", workshop_type=wt)
        p = Participant(email="p@example.com", full_name="P")
        db.session.add_all([wt, sess, p])
        db.session.flush()
        link = SessionParticipant(session_id=sess.id, participant_id=p.id)
        db.session.add(link)
        link_res = Resource(name="LinkR", type="LINK", resource_value="https://kt.com", active=True)
        doc_res = Resource(name="DocR", type="DOCUMENT", resource_value="doc.pdf", active=True)
        link_res.workshop_types.append(wt)
        doc_res.workshop_types.append(wt)
        db.session.add_all([link_res, doc_res])
        account = ParticipantAccount(email="p@example.com", full_name="P")
        db.session.add(account)
        db.session.commit()
        account_id = account.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["participant_account_id"] = account_id
    resp = client.get("/my-resources")
    html = resp.get_data(as_text=True)
    assert "Type A" in html
    assert "LinkR" in html and "https://kt.com" in html
    assert "/resources/doc.pdf" in html

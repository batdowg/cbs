import os
import sys

import pytest
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import (
    WorkshopType,
    Session,
    Participant,
    SessionParticipant,
    ParticipantAccount,
    Resource,
    User,
)
from app.forms.resource_forms import slugify_filename
from app.shared.html import sanitize_html


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
        wt = WorkshopType(code="ABC", name="Type A", cert_series="fn")
        today = date.today()
        sess = Session(title="S1", workshop_type=wt, start_date=today, end_date=today)
        p = Participant(email="p@example.com", full_name="P")
        db.session.add_all([wt, sess, p])
        db.session.flush()
        link = SessionParticipant(session_id=sess.id, participant_id=p.id)
        db.session.add(link)
        link_res = Resource(
            name="LinkR",
            type="LINK",
            resource_value="https://kt.com",
            active=True,
            description_html=sanitize_html("<p>Link <script>bad</script></p>"),
        )
        doc_res = Resource(
            name="DocR",
            type="DOCUMENT",
            resource_value="doc.pdf",
            active=True,
            description_html="",
        )
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
    assert '<summary class="resource-summary">LinkR</summary>' in html
    assert "https://kt.com" in html
    assert 'details class="resource-item"' in html
    assert "Open resource" in html
    assert '<div class="resource-description rich-text">' in html
    assert "<script>bad</script>" not in html
    assert "/resources/doc.pdf" in html
    assert "Download PDF" in html


def test_my_resources_staff_empty(app):
    with app.app_context():
        staff = User(email="staff@example.com", is_admin=True)
        db.session.add(staff)
        db.session.commit()
        user_id = staff.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    resp = client.get("/my-resources")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "No resources available." in html


def test_staff_nav_hides_my_resources_without_session(app):
    with app.app_context():
        staff = User(email="navstaff@example.com", is_admin=True)
        db.session.add(staff)
        db.session.commit()
        user_id = staff.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    resp = client.get("/home")
    assert b"My Resources" not in resp.data


def test_staff_nav_shows_my_resources_with_session(app):
    with app.app_context():
        staff = User(email="navfac@example.com", is_admin=True)
        wt = WorkshopType(code="NAV", name="Nav", cert_series="fn")
        today = date.today()
        sess = Session(
            title="S1",
            workshop_type=wt,
            start_date=today,
            end_date=today,
            lead_facilitator=staff,
        )
        db.session.add_all([staff, wt, sess])
        db.session.commit()
        user_id = staff.id
    client = app.test_client()
    with client.session_transaction() as sess_data:
        sess_data["user_id"] = user_id
    resp = client.get("/home")
    assert b"My Resources" in resp.data

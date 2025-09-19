import io
import os
import shutil
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
    ParticipantAccount,
    Resource,
    User,
)
from app.shared.html import sanitize_html
from app.shared.storage_resources import (
    resource_fs_dir,
    resource_web_url,
    sanitize_filename,
)


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv/resources", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


@pytest.mark.smoke
def test_resource_validation_and_sanitize(app):
    with app.app_context():
        r = Resource(
            name="Link",
            type="LINK",
            resource_value="https://example.com",
            audience="both",
            language="EN",
        )
        r.validate()
        assert r.audience == "Both"
        assert r.language == "en"
        r2 = Resource(name="Doc", type="DOCUMENT", resource_value="")
        with pytest.raises(ValueError):
            r2.validate()
        fname = sanitize_filename("My File.XLSX")
        assert fname.endswith(".xlsx")
        assert ".." not in fname


def test_my_resources_view(app):
    with app.app_context():
        wt = WorkshopType(code="ABC", name="Type A", cert_series="fn")
        today = date.today()
        sess = Session(
            title="S1",
            workshop_type=wt,
            start_date=today,
            end_date=today,
            workshop_language="en",
        )
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
            audience="Participant",
            language="en",
        )
        doc_res = Resource(
            name="DocR",
            type="DOCUMENT",
            resource_value="doc.pdf",
            active=True,
            description_html="",
            audience="Both",
            language="en",
        )
        hidden_res = Resource(
            name="Hidden",
            type="LINK",
            resource_value="https://hidden",  # should be filtered
            active=True,
            audience="Facilitator",
            language="en",
        )
        foreign_lang = Resource(
            name="Foreign",
            type="LINK",
            resource_value="https://foreign",
            active=True,
            audience="Participant",
            language="es",
        )
        link_res.workshop_types.append(wt)
        doc_res.workshop_types.append(wt)
        hidden_res.workshop_types.append(wt)
        foreign_lang.workshop_types.append(wt)
        db.session.add_all([link_res, doc_res, hidden_res, foreign_lang])
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
    assert "https://hidden" not in html
    assert "https://foreign" not in html


@pytest.mark.smoke
def test_resource_file_upload_persists(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        wt = WorkshopType(code="UPL", name="Upload WT", cert_series="fn")
        db.session.add_all([admin, wt])
        db.session.commit()
        admin_id = admin.id
        wt_id = wt.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id

    data = {
        "name": "Upload Resource",
        "type": "DOCUMENT",
        "link": "",
        "active": "y",
        "description": "<p>Upload</p>",
        "workshop_types": [str(wt_id)],
        "audience": "Facilitator",
        "language": "en",
    }
    upload_name = "Test Plan.PDF"
    response = client.post(
        "/settings/resources/new",
        data={**data, "file": (io.BytesIO(b"hello world"), upload_name)},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        res = Resource.query.filter_by(name="Upload Resource").one()
        expected_filename = sanitize_filename(upload_name)
        expected_url = resource_web_url(res.id, expected_filename)
        assert res.resource_value == expected_url
        fs_path = os.path.join(resource_fs_dir(res.id), expected_filename)
        assert os.path.exists(fs_path)
        with open(fs_path, "rb") as stored:
            assert stored.read() == b"hello world"

    download = client.get(expected_url)
    assert download.status_code == 200
    assert download.data == b"hello world"
    shutil.rmtree(resource_fs_dir(res.id), ignore_errors=True)


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


def test_workshop_view_facilitator_resources(app):
    with app.app_context():
        facilitator = User(email="fac@example.com", is_kt_delivery=True)
        facilitator.set_password("x")
        wt = WorkshopType(code="WRK", name="Workshop", cert_series="fn")
        sess = Session(
            title="Fac Session",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            lead_facilitator=facilitator,
        )
        sess.facilitators = [facilitator]
        fac_only = Resource(
            name="FacOnly",
            type="LINK",
            resource_value="https://fac",
            active=True,
            audience="Facilitator",
            language="en",
        )
        both = Resource(
            name="BothR",
            type="DOCUMENT",
            resource_value="doc.pdf",
            active=True,
            audience="Both",
            language="en",
        )
        participant_only = Resource(
            name="ParticipantOnly",
            type="LINK",
            resource_value="https://participant",
            active=True,
            audience="Participant",
            language="en",
        )
        other_lang = Resource(
            name="OtherLang",
            type="LINK",
            resource_value="https://es",
            active=True,
            audience="Facilitator",
            language="es",
        )
        fac_only.workshop_types.append(wt)
        both.workshop_types.append(wt)
        participant_only.workshop_types.append(wt)
        other_lang.workshop_types.append(wt)
        db.session.add_all(
            [facilitator, wt, sess, fac_only, both, participant_only, other_lang]
        )
        db.session.commit()
        session_id = sess.id
        facilitator_id = facilitator.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = facilitator_id
    resp = client.get(f"/workshops/{session_id}")
    html = resp.get_data(as_text=True)
    assert "FacOnly" in html
    assert "BothR" in html
    assert "ParticipantOnly" not in html
    assert "OtherLang" not in html

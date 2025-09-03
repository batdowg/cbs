import os
from datetime import date, time

import pytest

from app.app import create_app, db
from app.models import WorkshopType, Session, ParticipantAccount


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def _setup(app):
    with app.app_context():
        wt = WorkshopType(code="WT", name="WT")
        csa_acc = ParticipantAccount(email="csa@example.com", full_name="CSA", is_active=True)
        part_acc = ParticipantAccount(email="p@example.com", full_name="P", is_active=True)
        sess = Session(
            title="S",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            daily_start_time=time(9, 0),
            timezone="UTC",
            csa_account=csa_acc,
        )
        db.session.add_all([wt, csa_acc, part_acc, sess])
        db.session.commit()
        return csa_acc.id, part_acc.id, sess.id


def _login(client, account_id):
    with client.session_transaction() as sess:
        sess["participant_account_id"] = account_id


def test_csa_my_sessions_page(app):
    csa_id, part_id, sess_id = _setup(app)
    client = app.test_client()
    _login(client, csa_id)
    resp = client.get("/csa/my-sessions")
    assert b"My Sessions" in resp.data
    assert f"/sessions/{sess_id}".encode() in resp.data
    assert b"href=\"/csa/my-sessions\"" in resp.data
    form_chunk = resp.data.split(b'action="/settings/view"')[1].split(b'</form>')[0]
    assert b'<option value="CSA"' in form_chunk
    assert b'<option value="LEARNER"' in form_chunk
    assert form_chunk.count(b'<option') == 2


def test_csa_home_redirect(app):
    csa_id, part_id, sess_id = _setup(app)
    client = app.test_client()
    _login(client, csa_id)
    resp = client.get("/home")
    assert resp.status_code == 302
    assert "/csa/my-sessions" in resp.headers["Location"]


def test_participant_no_view_switcher(app):
    csa_id, part_id, sess_id = _setup(app)
    client = app.test_client()
    _login(client, part_id)
    resp = client.get("/home")
    assert b'action="/settings/view"' not in resp.data

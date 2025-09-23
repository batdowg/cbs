import os
import os
import sys
import pytest
from datetime import date, timedelta

pytestmark = pytest.mark.smoke

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import User, Session, WorkshopType


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_sessions_index_uses_computed_status(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, region="NA")
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        sess = Session(
            title="Sess",
            workshop_type=wt,
            start_date=date.today() - timedelta(days=2),
            end_date=date.today() - timedelta(days=1),
            region="NA",
            delivered=True,
        )
        db.session.add_all([admin, wt, sess])
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.get("/sessions")
    assert b"Delivered" in resp.data


def test_session_detail_finalize_button_visibility(app):
    with app.app_context():
        admin = User(email="admin2@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("secret")
        wt = WorkshopType(code="VIS", name="Visibility", cert_series="fn")
        sess = Session(
            title="Visibility Test",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            delivery_type="In person",
        )
        db.session.add_all([admin, wt, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id

    client_tc = app.test_client()
    login(client_tc, admin_id)

    resp = client_tc.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Finalize session" not in html

    resp = client_tc.post(
        f"/sessions/{session_id}/mark-delivered", follow_redirects=False
    )
    assert resp.status_code == 302

    resp = client_tc.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Finalize session" in html

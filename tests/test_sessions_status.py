import os
import sys
import pytest
from datetime import date, timedelta

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

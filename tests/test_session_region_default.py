import os
import pytest

from app.app import create_app, db
from app.models import User

pytestmark = pytest.mark.smoke


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_new_session_region_defaults(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True, region="EU")
        admin.set_password("x")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id
    resp = client.get("/sessions/new")
    assert b'<option value="EU" selected>' in resp.data

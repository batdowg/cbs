import os
import pytest

from app.app import create_app, db
from app.models import User, ProcessorAssignment

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


def test_processors_persist(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        user = User(email="u1@example.com")
        user.set_password("x")
        db.session.add_all([admin, user])
        db.session.commit()
        admin_id = admin.id
        u1_id = user.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id
    resp = client.post(
        "/mail-settings/processors",
        data={"NA-Digital": [str(u1_id)]},
    )
    assert resp.status_code == 302
    with app.app_context():
        rows = ProcessorAssignment.query.all()
        assert len(rows) == 1
        assert rows[0].region == "NA"
        assert rows[0].processing_type == "Digital"
        assert rows[0].user_id == u1_id

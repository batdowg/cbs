import os
import sys
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import User, ParticipantAccount
from manage import account_dupes

@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        app.cli.add_command(account_dupes)
        yield app
        db.session.remove()

def test_account_dupes_cli(app):
    with app.app_context():
        u = User(email="dupe@example.com", full_name="Staff", region="NA")
        u.set_password("pw")
        pa = ParticipantAccount(email="dupe@example.com", full_name="Learner", is_active=True)
        db.session.add_all([u, pa])
        db.session.commit()
    runner = app.test_cli_runner()
    res = runner.invoke(args=["account_dupes"])
    assert "dupe@example.com" in res.output
    res = runner.invoke(args=["account_dupes", "--fix-sync"])
    assert res.exit_code == 0
    with app.app_context():
        pa = ParticipantAccount.query.filter_by(email="dupe@example.com").one()
        assert pa.full_name == "Staff"

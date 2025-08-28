import pathlib
import sys

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.app import create_app, db
from app.models import Participant, ParticipantAccount
from app.utils import accounts as acct_utils


def test_ensure_account_case_insensitive_reuse():
    app = create_app()
    with app.app_context():
        db.create_all()
        existing = ParticipantAccount(email="p@example.com", full_name="P")
        db.session.add(existing)
        db.session.commit()
        p = Participant(email="P@Example.com", full_name="P2")
        db.session.add(p)
        db.session.commit()
        acct = acct_utils.ensure_participant_account(p, {})
        assert acct.id == existing.id
        assert ParticipantAccount.query.count() == 1


def test_ensure_account_integrity_error_fallback(monkeypatch):
    app = create_app()
    with app.app_context():
        db.create_all()
        existing = ParticipantAccount(email="i@example.com", full_name="I")
        db.session.add(existing)
        db.session.commit()
        p = Participant(email="i@example.com", full_name="I2")
        db.session.add(p)
        db.session.commit()
        orig = acct_utils.get_participant_account_by_email
        calls = {"n": 0}

        def fake_get(email: str):
            if calls["n"] == 0:
                calls["n"] += 1
                return None
            return orig(email)

        monkeypatch.setattr(acct_utils, "get_participant_account_by_email", fake_get)
        acct = acct_utils.ensure_participant_account(p, {})
        assert acct.id == existing.id
        assert ParticipantAccount.query.count() == 1

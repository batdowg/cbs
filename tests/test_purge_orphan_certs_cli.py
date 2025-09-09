import os
from datetime import date
from pathlib import Path

import pytest
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import Certificate, Session, Participant, ParticipantAccount
from manage import purge_orphan_certs


@pytest.fixture
def app(tmp_path):
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["SITE_ROOT"] = str(tmp_path)
    os.environ["FLASK_ENV"] = "development"
    app = create_app()
    with app.app_context():
        db.create_all()
        app.cli.add_command(purge_orphan_certs)
        yield app
        db.session.remove()


def _setup_files(app, root: Path):
    cert_dir = root / "certificates" / "2024" / "1"
    cert_dir.mkdir(parents=True)
    kept_path = cert_dir / "keep.pdf"
    kept_path.write_bytes(b"x")
    orphan_path = cert_dir / "orphan.pdf"
    orphan_path.write_bytes(b"x")
    with app.app_context():
        acct = ParticipantAccount(
            id=1, email="a@example.com", full_name="A", is_active=True
        )
        part = Participant(id=1, account_id=1, email="a@example.com")
        sess = Session(id=1, title="s", start_date=date.today())
        db.session.add_all([acct, part, sess])
        db.session.commit()
        rel = os.path.relpath(kept_path, root)
        db.session.add(
            Certificate(
                participant_id=1,
                session_id=1,
                pdf_path=rel,
                certificate_name="a",
                workshop_name="w",
                workshop_date=date.today(),
            )
        )
        db.session.commit()
    return kept_path, orphan_path


def test_purge_orphan_certs_cli(app, tmp_path):
    kept, orphan = _setup_files(app, tmp_path)
    runner = app.test_cli_runner()
    res = runner.invoke(args=["purge_orphan_certs", "--dry-run"])
    assert "orphan.pdf" in res.output
    assert orphan.exists()
    res = runner.invoke(args=["purge_orphan_certs"])
    assert res.exit_code == 0
    assert not orphan.exists()
    assert kept.exists()

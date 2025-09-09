from app.app import create_app, db
import os

from flask_migrate import Migrate
from flask.cli import FlaskGroup
import click
from sqlalchemy import func
from flask import current_app
from app.shared.certificates import render_certificate
from app.models import Session, ParticipantAccount, User, Certificate


migrate = Migrate()


def create_cbs_app():
    app = create_app()
    migrate.init_app(app, db)
    return app


cli = FlaskGroup(create_app=create_cbs_app)


@cli.command("gen_cert")
@click.option("--session", "session_id", required=True, type=int)
@click.option("--email", "email", required=True)
def gen_cert(session_id: int, email: str):
    """Generate a certificate for a participant."""
    sess = db.session.get(Session, session_id)
    acct = (
        db.session.query(ParticipantAccount)
        .filter(func.lower(ParticipantAccount.email) == email.lower())
        .one_or_none()
    )
    if not sess or not acct:
        click.echo("Not found", err=True)
        return
    path = render_certificate(sess, acct)
    click.echo(path)


@cli.command("account_dupes")
@click.option(
    "--fix-sync",
    is_flag=True,
    help="Sync User.full_name to ParticipantAccount.full_name",
)
def account_dupes(fix_sync: bool):
    rows = (
        db.session.query(User, ParticipantAccount)
        .join(
            ParticipantAccount,
            func.lower(User.email) == func.lower(ParticipantAccount.email),
        )
        .all()
    )
    if not rows:
        click.echo("No duplicates")
        return
    for user, acct in rows:
        click.echo(
            f"{user.email} user_id={user.id} name={user.full_name} | pa_id={acct.id} name={acct.full_name}"
        )
        if fix_sync:
            acct.full_name = user.full_name
    if fix_sync:
        db.session.commit()
        click.echo("Names synced")


@cli.command("purge_orphan_certs")
@click.option(
    "--dry-run", is_flag=True, help="List orphaned certificate PDFs without deleting"
)
def purge_orphan_certs(dry_run: bool):
    site_root = current_app.config.get("SITE_ROOT", "/srv")
    cert_root = os.path.join(site_root, "certificates")
    if not os.path.isdir(cert_root):
        click.echo("Certificate directory missing", err=True)
        return
    if (
        not dry_run
        and current_app.config.get("ENV") == "production"
        and os.getenv("ALLOW_CERT_PURGE") != "1"
    ):
        click.echo(
            "Refusing to delete in production without ALLOW_CERT_PURGE=1", err=True
        )
        return

    total = deleted = kept = errors = 0
    samples: list[str] = []
    for root, dirs, files in os.walk(cert_root):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for name in files:
            if not name.lower().endswith(".pdf"):
                continue
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, site_root)
            total += 1
            exists = (
                db.session.query(Certificate.id).filter_by(pdf_path=rel_path).first()
            )
            if exists:
                kept += 1
                continue
            if len(samples) < 5:
                samples.append(full_path)
            if dry_run:
                continue
            try:
                os.remove(full_path)
                deleted += 1
            except Exception:
                errors += 1
                current_app.logger.exception(
                    "[CERT-PURGE] failed to remove %s", full_path
                )
    summary = f"scanned={total} deleted={deleted} kept={kept} errors={errors}"
    for path in samples:
        click.echo(path)
    click.echo(summary)
    current_app.logger.info("[CERT-PURGE] %s", summary)


if __name__ == "__main__":
    cli()

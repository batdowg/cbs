from app.app import create_app, db
from flask_migrate import Migrate
from flask.cli import FlaskGroup
import click
from sqlalchemy import func
from app.shared.certificates import render_certificate
from app.models import Session, ParticipantAccount, User


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
@click.option("--fix-sync", is_flag=True, help="Sync User.full_name to ParticipantAccount.full_name")
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


if __name__ == "__main__":
    cli()


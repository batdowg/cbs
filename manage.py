from app.app import create_app, db
from flask_migrate import Migrate
from flask.cli import FlaskGroup
import click
from sqlalchemy import func
from app.utils.certificates import render_certificate
from app.models import Session, ParticipantAccount


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


if __name__ == "__main__":
    cli()


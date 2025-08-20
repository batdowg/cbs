from app.app import create_app, db
from flask_migrate import Migrate
from flask.cli import FlaskGroup


migrate = Migrate()


def create_cbs_app():
    app = create_app()
    migrate.init_app(app, db)
    return app


cli = FlaskGroup(create_app=create_cbs_app)


if __name__ == "__main__":
    cli()


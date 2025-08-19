"""Flask CLI entry point for migration commands."""

from flask_migrate import Migrate

from app.app import create_app, db

app = create_app()
migrate = Migrate(app, db)


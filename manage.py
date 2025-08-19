"""Flask CLI entry point for migration commands."""

from app.app import create_app, db  # noqa: F401

app = create_app()


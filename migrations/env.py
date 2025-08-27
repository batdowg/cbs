from __future__ import with_statement

import logging
from logging.config import fileConfig

from alembic import context
from app.app import create_app, db

config = context.config

fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")

app = create_app()

with app.app_context():
    target_metadata = db.metadata


def run_migrations_offline() -> None:
    with app.app_context():
        url = config.get_main_option("sqlalchemy.url")
        if not url:
            url = app.config["SQLALCHEMY_DATABASE_URI"]
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )

        with context.begin_transaction():
            context.run_migrations()


def run_migrations_online() -> None:
    with app.app_context():
        connectable = db.engine

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

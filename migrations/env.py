from __future__ import with_statement

import logging
from logging.config import fileConfig

from flask import current_app
from alembic import context

config = context.config

fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")

target_metadata = current_app.extensions["migrate"].db.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = str(current_app.extensions["migrate"].db.engine.url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = current_app.extensions["migrate"].db.engine

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


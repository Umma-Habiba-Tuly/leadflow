"""Alembic environment: points migrations at our models and our DATABASE_URL."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db import models  # noqa: F401  (importing registers every table on Base.metadata)
from app.db.session import Base

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False: the default would silence our app's loggers.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    # Tests (and one-off scripts) can override with config.set_main_option("sqlalchemy.url", ...).
    return config.get_main_option("sqlalchemy.url") or settings.database_url


# render_as_batch: SQLite can't ALTER most things in place, so Alembic recreates the table
# ("batch mode"). It is a no-op on Postgres. compare_type: notice column type changes too.
_COMMON = dict(target_metadata=target_metadata, render_as_batch=True, compare_type=True)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of touching a database (`alembic upgrade head --sql`)."""
    context.configure(url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"}, **_COMMON)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, **_COMMON)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

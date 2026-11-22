"""Guards for the database migrations.

The big one is the drift check: running the migrations must produce exactly the schema the
models describe. If someone edits a model and forgets the migration, this fails here
instead of in production.
"""
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.session import Base

BACKEND = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture()
def db(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    engine = create_engine(url)
    yield url, engine
    engine.dispose()


def test_upgrade_creates_every_model_table(db):
    url, engine = db
    command.upgrade(alembic_config(url), "head")
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}


def test_migrations_match_the_models_exactly(db):
    """No drift: nothing a model declares is missing from the migrated database."""
    url, engine = db
    command.upgrade(alembic_config(url), "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"Models and migrations disagree. Run `alembic revision --autogenerate`: {diff}"


def test_there_is_exactly_one_head(db):
    """Two heads means two people made migrations in parallel; they must be merged."""
    heads = ScriptDirectory.from_config(alembic_config("sqlite://")).get_heads()
    assert len(heads) == 1, f"Migration branches need merging: {heads}"


def test_downgrade_removes_everything_and_upgrade_works_again(db):
    url, engine = db
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    command.upgrade(cfg, "head")
    assert "leads" in inspect(engine).get_table_names()


def test_upgrading_again_is_a_safe_no_op_and_keeps_data(db):
    url, engine = db
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        conn.execute(text("insert into workspaces (name, created_at) values ('Acme', '2026-01-01')"))
    command.upgrade(cfg, "head")  # what every deploy does
    with engine.connect() as conn:
        assert conn.execute(text("select name from workspaces")).scalar() == "Acme"


def test_every_constraint_has_a_name(db):
    """Anonymous constraints can't be altered later on SQLite. The naming convention prevents it."""
    url, engine = db
    command.upgrade(alembic_config(url), "head")
    insp = inspect(engine)
    for table in Base.metadata.tables:
        for fk in insp.get_foreign_keys(table):
            assert fk["name"], f"{table} has an unnamed foreign key"
        for uq in insp.get_unique_constraints(table):
            assert uq["name"], f"{table} has an unnamed unique constraint"


def test_an_existing_database_can_be_adopted_with_stamp(db):
    """The path for a database made before Alembic existed (like the old dev DB): mark it as
    already at head instead of running migrations that would try to recreate its tables."""
    url, engine = db
    Base.metadata.create_all(engine)  # the old way
    with engine.begin() as conn:
        conn.execute(text("insert into workspaces (name, created_at) values ('Legacy', '2026-01-01')"))
    cfg = alembic_config(url)

    # Running the migration as-is collides with the tables that already exist.
    with pytest.raises(OperationalError, match="already exists"):
        command.upgrade(cfg, "head")

    command.stamp(cfg, "head")
    command.upgrade(cfg, "head")  # now a no-op
    with engine.connect() as conn:
        assert conn.execute(text("select name from workspaces")).scalar() == "Legacy"
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []

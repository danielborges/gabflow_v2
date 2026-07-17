import os
from pathlib import Path

import pytest
from flask_migrate import upgrade
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app import create_app
from app.config import Config
from app.extensions import db

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[2] / "migrations"


def _postgres_test_database_url() -> str:
    database_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is required for PostgreSQL integration tests")

    parsed_url = make_url(database_url)
    if not parsed_url.drivername.startswith("postgresql"):
        pytest.fail("POSTGRES_TEST_DATABASE_URL must use PostgreSQL")

    database_name = parsed_url.database or ""
    if not database_name.endswith(("_test", "_ci")):
        pytest.fail("PostgreSQL integration database name must end with _test or _ci")

    return database_url


def _reset_public_schema() -> None:
    db.session.remove()
    with db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


@pytest.fixture()
def postgres_app(tmp_path):
    database_url = _postgres_test_database_url()
    config = type(
        "PostgresTestConfig",
        (Config,),
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": database_url,
            "JWT_COOKIE_SECURE": False,
            "RATELIMIT_ENABLED": False,
            "SENTRY_DSN": None,
            "RESEND_API_KEY": None,
            "RESEND_FROM_EMAIL": None,
            "ATTACHMENT_STORAGE_PATH": str(tmp_path / "attachments"),
            "RAG_STORAGE_PATH": str(tmp_path / "rag"),
        },
    )
    application = create_app(config)

    with application.app_context():
        _reset_public_schema()
        upgrade(directory=str(MIGRATIONS_DIRECTORY))

    yield application

    with application.app_context():
        _reset_public_schema()

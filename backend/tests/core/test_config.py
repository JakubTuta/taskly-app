from pathlib import Path

import pytest

from app.core import config
from app.core.config import resolve_database_url

DATABASE_VARIABLES = ["DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "DB_PORT", "POSTGRES_DB"]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in DATABASE_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    dotenv_calls = []
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: dotenv_calls.append((args, kwargs)))
    return dotenv_calls


@pytest.fixture
def postgres_parts(monkeypatch):
    values = {
        "POSTGRES_USER": "taskly",
        "POSTGRES_PASSWORD": "taskly",
        "POSTGRES_HOST": "db.internal",
        "DB_PORT": "6543",
        "POSTGRES_DB": "tasks",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_explicit_url_takes_precedence_over_the_environment(monkeypatch, postgres_parts):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://env/ignored")
    assert resolve_database_url("sqlite://") == "sqlite://"


def test_uses_database_url_from_the_environment(monkeypatch, postgres_parts):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://from-env/db")
    assert resolve_database_url() == "postgresql+psycopg://from-env/db"


def test_builds_a_psycopg_url_from_postgres_variables(postgres_parts):
    assert resolve_database_url() == "postgresql+psycopg://taskly:taskly@db.internal:6543/tasks"


def test_escapes_special_characters_in_credentials(monkeypatch, postgres_parts):
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss:w/rd")
    assert resolve_database_url() == "postgresql+psycopg://taskly:p%40ss%3Aw%2Frd@db.internal:6543/tasks"


@pytest.mark.parametrize("missing", ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "DB_PORT", "POSTGRES_DB"])
def test_requires_every_postgres_variable_without_database_url(monkeypatch, postgres_parts, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(KeyError, match=missing):
        resolve_database_url()


def test_rejects_a_non_numeric_port(monkeypatch, postgres_parts):
    monkeypatch.setenv("DB_PORT", "postgres")
    with pytest.raises(ValueError):
        resolve_database_url()


def test_loads_the_repository_env_file_without_overriding_existing_variables(isolated_environment):
    resolve_database_url("sqlite://")
    repository_root = Path(__file__).resolve().parents[3]
    assert isolated_environment == [((repository_root / ".env",), {"override": False})]

from unittest.mock import Mock, sentinel

from sqlalchemy import create_engine, inspect

from app.core import database
from app.core.database import create_database_engine, create_session_factory, initialize


def test_engine_uses_the_postgresql_psycopg_driver():
    url = "postgresql+psycopg://taskly:taskly@localhost:5432/taskly"
    engine = create_database_engine(url)
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
        assert engine.url.database == "taskly"
    finally:
        engine.dispose()


def test_engine_checks_connections_before_use_and_limits_connect_time(monkeypatch):
    factory = Mock(return_value=sentinel.engine)
    monkeypatch.setattr(database, "create_engine", factory)
    assert create_database_engine("postgresql+psycopg://db/taskly") is sentinel.engine
    factory.assert_called_once_with(
        "postgresql+psycopg://db/taskly", pool_pre_ping=True, connect_args={"connect_timeout": 10}
    )


def test_session_factory_binds_sessions_to_the_engine_and_keeps_objects_loaded_after_commit():
    engine = create_engine("sqlite://")
    try:
        with create_session_factory(engine)() as session:
            assert session.get_bind() is engine
            assert session.expire_on_commit is False
    finally:
        engine.dispose()


def test_initialize_creates_the_todos_table():
    engine = create_engine("sqlite://")
    try:
        initialize(engine)
        inspector = inspect(engine)
        assert inspector.get_table_names() == ["todos"]
        assert {column["name"] for column in inspector.get_columns("todos")} == {
            "id", "title", "description", "priority", "due_date", "completed", "created_at", "updated_at",
        }
    finally:
        engine.dispose()


def test_initialize_keeps_existing_tables():
    engine = create_engine("sqlite://")
    try:
        initialize(engine)
        initialize(engine)
        assert inspect(engine).get_table_names() == ["todos"]
    finally:
        engine.dispose()

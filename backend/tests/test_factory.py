from unittest.mock import Mock, sentinel

import pytest
from fastapi.testclient import TestClient

from app.factory import create_app


@pytest.fixture
def resolve(monkeypatch):
    resolver = Mock(return_value="postgresql+psycopg://resolved/taskly")
    monkeypatch.setattr("app.factory.resolve_database_url", resolver)
    return resolver


@pytest.mark.parametrize("database_url", [None, "sqlite://"])
def test_resolves_and_stores_the_database_url(resolve, database_url):
    app = create_app(database_url)
    resolve.assert_called_once_with(database_url)
    assert app.state.database_url == "postgresql+psycopg://resolved/taskly"


def test_exposes_health_and_todo_routes(resolve):
    app = create_app()
    schema = app.openapi()
    routes = {(path, method.upper()) for path, operations in schema["paths"].items() for method in operations}
    assert (schema["info"]["title"], schema["info"]["version"]) == ("Taskly API", "1.0.0")
    assert routes == {
        ("/api/health", "GET"),
        ("/api/todos", "GET"),
        ("/api/todos", "POST"),
        ("/api/todos/{todo_id}", "GET"),
        ("/api/todos/{todo_id}", "PATCH"),
        ("/api/todos/{todo_id}", "DELETE"),
    }


def test_starting_the_app_prepares_the_database_from_the_resolved_url(resolve, monkeypatch):
    engine = Mock()
    create_engine = Mock(return_value=engine)
    initialize = Mock()
    monkeypatch.setattr("app.core.lifespan.create_database_engine", create_engine)
    monkeypatch.setattr("app.core.lifespan.initialize", initialize)
    monkeypatch.setattr("app.core.lifespan.create_session_factory", Mock(return_value=sentinel.factory))
    app = create_app()
    with TestClient(app):
        create_engine.assert_called_once_with("postgresql+psycopg://resolved/taskly")
        initialize.assert_called_once_with(engine)
        assert app.state.session_factory is sentinel.factory
    engine.dispose.assert_called_once_with()

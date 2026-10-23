import asyncio
from unittest.mock import Mock, call, sentinel

import pytest
from fastapi import FastAPI

from app.core.lifespan import lifespan


@pytest.fixture
def collaborators(monkeypatch):
    engine = Mock()
    tracker = Mock()
    tracker.create_database_engine.return_value = engine
    tracker.create_session_factory.return_value = sentinel.session_factory
    tracker.attach_mock(engine.dispose, "dispose")
    for name in ("create_database_engine", "initialize", "create_session_factory"):
        monkeypatch.setattr(f"app.core.lifespan.{name}", getattr(tracker, name))
    return tracker, engine


@pytest.fixture
def app():
    application = FastAPI()
    application.state.database_url = "postgresql+psycopg://taskly@db/taskly"
    return application


def run_lifespan(app, body=None):
    async def scenario():
        async with lifespan(app):
            if body:
                body()

    asyncio.run(scenario())


def test_prepares_the_database_on_startup_and_disposes_the_engine_on_shutdown(app, collaborators):
    tracker, engine = collaborators
    seen_during_startup = {}

    def capture():
        seen_during_startup["factory"] = app.state.session_factory
        seen_during_startup["disposed"] = engine.dispose.called

    run_lifespan(app, capture)
    assert seen_during_startup == {"factory": sentinel.session_factory, "disposed": False}
    assert tracker.mock_calls == [
        call.create_database_engine("postgresql+psycopg://taskly@db/taskly"),
        call.initialize(engine),
        call.create_session_factory(engine),
        call.dispose(),
    ]


def test_disposes_the_engine_when_initialization_fails(app, collaborators):
    tracker, engine = collaborators
    tracker.initialize.side_effect = RuntimeError("Database unavailable")
    with pytest.raises(RuntimeError, match="Database unavailable"):
        run_lifespan(app)
    engine.dispose.assert_called_once_with()
    tracker.create_session_factory.assert_not_called()
    assert not hasattr(app.state, "session_factory")


def test_disposes_the_engine_when_the_application_fails(app, collaborators):
    _, engine = collaborators

    def crash():
        raise RuntimeError("Application crashed")

    with pytest.raises(RuntimeError, match="Application crashed"):
        run_lifespan(app, crash)
    engine.dispose.assert_called_once_with()

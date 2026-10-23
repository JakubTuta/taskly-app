from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.dependencies import get_repository
from app.features.todos.repository import TodoRepository


def make_request(session_factory):
    app = SimpleNamespace(state=SimpleNamespace(session_factory=session_factory))
    return Request({"type": "http", "app": app})


def test_session_creation_failure_propagates_from_repository_dependency():
    session_factory = Mock(side_effect=RuntimeError("Session unavailable"))
    app = SimpleNamespace(state=SimpleNamespace(session_factory=session_factory))
    request = Request({"type": "http", "app": app})
    dependency = get_repository(request)
    with pytest.raises(RuntimeError, match="Session unavailable"):
        next(dependency)
    session_factory.assert_called_once_with()


def test_yields_a_repository_bound_to_a_new_session_and_closes_it_after_the_request():
    session = Mock(spec=Session)
    dependency = get_repository(make_request(Mock(return_value=session)))
    repository = next(dependency)
    assert isinstance(repository, TodoRepository)
    assert repository.session is session
    session.close.assert_not_called()
    with pytest.raises(StopIteration):
        next(dependency)
    assert session.mock_calls == [call.close()]


def test_rolls_back_then_closes_the_session_when_the_request_fails():
    session = Mock(spec=Session)
    dependency = get_repository(make_request(Mock(return_value=session)))
    next(dependency)
    with pytest.raises(ValueError, match="Request failed"):
        dependency.throw(ValueError("Request failed"))
    assert session.mock_calls == [call.rollback(), call.close()]


def test_closes_the_session_without_rollback_when_the_dependency_is_cancelled():
    session = Mock(spec=Session)
    dependency = get_repository(make_request(Mock(return_value=session)))
    next(dependency)
    dependency.close()
    assert session.mock_calls == [call.close()]

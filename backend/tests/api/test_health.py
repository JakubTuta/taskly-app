from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.dependencies import get_repository
from app.api.health import router
from app.features.todos.models import TodoRecord


@pytest.fixture
def session(repository_mock):
    repository_mock.session = Mock(spec=Session)
    return repository_mock.session


@pytest.fixture
def health_client(repository_mock, session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository] = lambda: repository_mock
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_reports_ok_after_querying_the_database(health_client, session):
    response = health_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    session.execute.assert_called_once()
    statement = session.execute.call_args.args[0]
    assert statement.compare(select(TodoRecord.id).limit(1))


def test_fails_when_the_database_cannot_be_queried(health_client, session):
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("connection refused"))
    response = health_client.get("/api/health")
    assert response.status_code == 500
    assert response.text != '{"status":"ok"}'

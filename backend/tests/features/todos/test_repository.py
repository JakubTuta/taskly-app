from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.features.todos.models import TodoRecord
from app.features.todos.repository import TodoRepository
from app.features.todos.schemas import Priority, TodoCreate, TodoUpdate


@pytest.fixture
def session():
    return Mock(spec=Session)


@pytest.fixture
def stored(model_factory, todo_values, session):
    record = model_factory({**todo_values, "due_date": date(2026, 10, 20)})
    session.get.return_value = record
    return record


def test_list_maps_models_and_orders_tasks_newest_first(model_factory, todo_values, todo):
    session = Mock(spec=Session)
    session.scalars.return_value = [model_factory(todo_values)]
    assert TodoRepository(session).list() == [todo]
    statement = session.scalars.call_args.args[0]
    expected = select(TodoRecord).order_by(TodoRecord.created_at.desc(), TodoRecord.id.desc())
    assert statement.compare(expected)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY todos.created_at DESC, todos.id DESC" in compiled


def test_get_returns_none_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None
    assert TodoRepository(session).get(404) is None
    session.get.assert_called_once_with(TodoRecord, 404)


def test_get_maps_the_stored_task(session, stored):
    todo = TodoRepository(session).get(7)
    assert todo.id == 7
    assert todo.title == "Plan the sprint"
    assert todo.due_date == date(2026, 10, 20)
    session.get.assert_called_once_with(TodoRecord, 7)


def test_create_persists_the_payload_with_matching_utc_timestamps(session):
    session.refresh.side_effect = lambda record: setattr(record, "id", 42)
    before = datetime.now(timezone.utc)
    todo = TodoRepository(session).create(TodoCreate(title="Write tests", priority="high", due_date="2026-11-01"))
    after = datetime.now(timezone.utc)
    record = session.add.call_args.args[0]
    assert isinstance(record, TodoRecord)
    assert [name for name, _, _ in session.mock_calls] == ["add", "commit", "refresh"]
    session.refresh.assert_called_once_with(record)
    assert todo.id == 42
    assert (todo.title, todo.description, todo.priority, todo.completed) == ("Write tests", "", Priority.high, False)
    assert todo.due_date == date(2026, 11, 1)
    assert todo.created_at == todo.updated_at
    assert todo.created_at.tzinfo is not None
    assert before <= todo.created_at <= after


def test_update_returns_none_without_committing_when_task_is_missing(session):
    session.get.return_value = None
    assert TodoRepository(session).update(404, TodoUpdate(completed=True)) is None
    session.commit.assert_not_called()


def test_update_changes_only_the_fields_present_in_the_patch(session, stored, todo_values):
    before = datetime.now(timezone.utc)
    todo = TodoRepository(session).update(7, TodoUpdate(completed=True))
    assert todo.completed is True
    assert (todo.title, todo.description, todo.priority) == ("Plan the sprint", "First scenario", Priority.high)
    assert todo.due_date == date(2026, 10, 20)
    assert todo.created_at == todo_values["created_at"]
    assert todo.updated_at >= before
    assert [name for name, _, _ in session.mock_calls] == ["get", "commit", "refresh"]
    session.refresh.assert_called_once_with(stored)


def test_update_can_clear_the_due_date(session, stored):
    todo = TodoRepository(session).update(7, TodoUpdate(due_date=None, title="Renamed"))
    assert todo.due_date is None
    assert todo.title == "Renamed"
    assert stored.due_date is None


def test_delete_returns_false_without_committing_when_task_is_missing(session):
    session.get.return_value = None
    assert TodoRepository(session).delete(404) is False
    session.delete.assert_not_called()
    session.commit.assert_not_called()


def test_delete_removes_the_task_and_commits(session, stored):
    assert TodoRepository(session).delete(7) is True
    session.get.assert_called_once_with(TodoRecord, 7)
    session.delete.assert_called_once_with(stored)
    session.commit.assert_called_once_with()

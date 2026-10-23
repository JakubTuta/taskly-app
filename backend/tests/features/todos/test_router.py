import pytest

from app.features.todos.schemas import TodoCreate, TodoUpdate


def test_list_returns_tasks_from_repository(client, repository_mock, todo):
    repository_mock.list.return_value = [todo]
    response = client.get("/api/todos")
    assert response.status_code == 200
    assert response.json() == [todo.model_dump(mode="json")]
    repository_mock.list.assert_called_once_with()


def test_create_trims_input_and_returns_created_task(client, repository_mock, todo):
    repository_mock.create.return_value = todo
    response = client.post("/api/todos", json={"title": "  Plan the sprint  ", "priority": "high"})
    assert response.status_code == 201
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.create.assert_called_once_with(
        TodoCreate(title="Plan the sprint", priority="high")
    )


@pytest.mark.parametrize("payload", [
    {"title": "   "},
    {"title": "x" * 121},
    {"title": "Task", "priority": "urgent"},
    {"title": "Task", "due_date": "2026-02-30"},
    {"title": "Task", "description": "x" * 2001},
    {"title": "Task", "completed": "yes"},
    {"title": "Task", "id": 1},
    {},
])
def test_invalid_create_never_calls_repository(client, repository_mock, payload):
    assert client.post("/api/todos", json=payload).status_code == 422
    repository_mock.create.assert_not_called()


def test_get_returns_the_requested_task(client, repository_mock, todo):
    repository_mock.get.return_value = todo
    response = client.get("/api/todos/7")
    assert response.status_code == 200
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.get.assert_called_once_with(7)


def test_get_returns_404_for_a_missing_task(client, repository_mock):
    repository_mock.get.return_value = None
    response = client.get("/api/todos/404")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
@pytest.mark.parametrize("todo_id", ["0", "-1", "abc"])
def test_rejects_invalid_task_ids_before_reaching_the_repository(client, repository_mock, method, todo_id):
    kwargs = {"json": {"completed": True}} if method == "patch" else {}
    response = client.request(method.upper(), f"/api/todos/{todo_id}", **kwargs)
    assert response.status_code == 422
    assert repository_mock.method_calls == []


def test_update_applies_a_trimmed_patch_and_returns_the_task(client, repository_mock, todo):
    updated = todo.model_copy(update={"title": "Renamed", "completed": True})
    repository_mock.update.return_value = updated
    response = client.patch("/api/todos/7", json={"title": "  Renamed  ", "completed": True})
    assert response.status_code == 200
    assert response.json() == updated.model_dump(mode="json")
    repository_mock.update.assert_called_once_with(7, TodoUpdate(title="Renamed", completed=True))
    assert repository_mock.update.call_args.args[1].model_fields_set == {"title", "completed"}


def test_update_returns_404_when_task_is_missing(client, repository_mock):
    repository_mock.update.return_value = None
    response = client.patch("/api/todos/404", json={"completed": True})
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}
    repository_mock.update.assert_called_once_with(404, TodoUpdate(completed=True))


@pytest.mark.parametrize("payload", [
    {},
    {"title": None},
    {"completed": None},
    {"title": ""},
    {"priority": "urgent"},
    {"completed": "true"},
    {"created_at": "2026-10-01T12:00:00Z"},
])
def test_invalid_update_never_calls_repository(client, repository_mock, payload):
    assert client.patch("/api/todos/7", json=payload).status_code == 422
    repository_mock.update.assert_not_called()


def test_delete_returns_204_without_a_body(client, repository_mock):
    repository_mock.delete.return_value = True
    response = client.delete("/api/todos/7")
    assert response.status_code == 204
    assert response.content == b""
    repository_mock.delete.assert_called_once_with(7)


def test_delete_returns_404_when_task_is_missing(client, repository_mock):
    repository_mock.delete.return_value = False
    response = client.delete("/api/todos/404")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}

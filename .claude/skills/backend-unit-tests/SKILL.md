---
name: backend-unit-tests
description: Conventions and patterns for writing pytest unit tests for the Taskly FastAPI backend (routers, repository, dependencies, config, lifespan, validators). Use before creating or editing any file under backend/tests.
when_to_use: Writing or updating backend tests, testing FastAPI endpoints, SQLAlchemy repository code, Pydantic validation, configuration or startup code.
---

# Backend unit tests (pytest + FastAPI)

## Layout and style

- Tests mirror the package: `backend/app/<pkg>/<module>.py` → `backend/tests/<pkg>/test_<module>.py`.
  Every test directory has an empty `__init__.py`; add one when you create a directory.
- Plain `def test_<behaviour>()` functions, no classes. The name states the behaviour:
  `test_update_returns_404_for_missing_task`, not `test_update_2`.
- `@pytest.mark.parametrize` for input matrices (invalid payloads, each nullable field, …).
- No comments or docstrings; names and assertions carry the intent. Imports sorted
  stdlib → third-party → `app` → `tests`. Lines up to ~110 characters.
- No real Postgres, network or `.env`. Tests must pass on a machine with no services running.

## Shared fixtures (`tests/conftest.py`, `tests/mocks.py`)

| Fixture | Use |
| --- | --- |
| `repository_mock` | `create_autospec(TodoRepository, instance=True)`; calls with wrong signatures fail. |
| `client` | `TestClient` for an app that mounts **only** the todos router with `get_repository` overridden by `repository_mock`. |
| `todo_values` | Dict of a stored task (id 7, UTC timestamps). |
| `todo` | `Todo` schema built from `todo_values`. |
| `model_factory` | `lambda values: TodoRecord(**values)` for ORM records. |

Reuse them; add new shared fixtures to `conftest.py` only when two or more files need them.

## Patterns by layer

**Routers** — drive HTTP through `client`; assert status, JSON body and the exact repository call.
Invalid input must return 422 *and* never reach the repository.

```python
def test_update_returns_404_when_task_is_missing(client, repository_mock):
    repository_mock.update.return_value = None
    response = client.patch("/api/todos/404", json={"completed": True})
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}
    repository_mock.update.assert_called_once_with(404, TodoUpdate(completed=True))
```

For routers outside the todos router (e.g. health), build a minimal `FastAPI()` in the test,
include that router and override `get_repository` the same way `conftest.client` does.

**Repository** — `Mock(spec=Session)`; assert `add/commit/refresh/delete` calls and the mapped
`Todo` result. Simulate database-assigned values in `session.refresh.side_effect`. For timestamps,
assert they are timezone-aware UTC and between two `datetime.now(timezone.utc)` bounds instead
of patching `datetime`.

**Dependencies / generators** — call the generator directly (`next(gen)`), then `gen.close()` or
`gen.throw(exc)` to exercise `finally` and `except` paths; assert `rollback`/`close` calls.

**Configuration** — `monkeypatch.setenv/delenv` for every variable the code reads and
`monkeypatch.setattr("app.core.config.load_dotenv", lambda *a, **k: None)` so a developer's
`.env` never leaks into results. Assert the rendered URL, including escaping of special characters.

**Lifespan / factory** — `monkeypatch.setattr` the collaborators *in the module under test*
(`app.core.lifespan.create_database_engine`, …), run the async context manager with
`asyncio.run(...)` (pytest-asyncio is not installed), and assert ordering and cleanup on error.

**SQLAlchemy metadata** — when a test needs a real engine (e.g. `initialize` creating tables),
use in-memory SQLite (`create_engine("sqlite://")`) and inspect it with `sqlalchemy.inspect`.

**Validation** — Pydantic errors surface as `ValidationError`; use `pytest.raises(..., match=...)`
on the message the code produces.

## Checklist before running

- Each changed branch has a test that would fail if the branch were deleted or inverted.
- Assertions check outcomes, not just that a mock was called.
- Error paths (404, 422, exceptions, rollback) are covered alongside the happy path.
- Run with the `run-tests` skill: first the file, then `--suite backend --coverage --repeat 2`.

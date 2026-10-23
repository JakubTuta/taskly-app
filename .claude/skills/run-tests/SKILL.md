---
name: run-tests
description: Run backend (pytest) and frontend (Vitest) unit tests — whole suites or selected files — with optional coverage, TypeScript type-checking and repeated runs for flakiness, producing a JSON report. Use whenever tests must be executed or verified.
when_to_use: After writing or changing tests, before reporting results, to measure coverage, or to check for flaky tests.
argument-hint: "[--suite backend|frontend|all] [--coverage] [--typecheck] [--repeat N] [paths...]"
allowed-tools: Bash(python3 .claude/skills/run-tests/scripts/run_tests.py *) Read
---

# Run tests

One entry point for both stacks, so every run (agent, workflow, developer) is executed and
judged the same way. Test processes get a sanitized environment: only an allowlist of
variables is passed through, so credentials in the caller's environment never reach test code.

## Commands

Targeted run while iterating (the suite is inferred from the path):

```bash
python3 .claude/skills/run-tests/scripts/run_tests.py backend/tests/features/todos/test_router.py
python3 .claude/skills/run-tests/scripts/run_tests.py frontend/src/lib/http.test.ts
```

Final verification — affected suites, coverage, type-check, two runs to catch flakiness:

```bash
python3 .claude/skills/run-tests/scripts/run_tests.py --suite all --coverage --typecheck --repeat 2
```

On Windows use `python` instead of `python3`.

Prerequisites: backend dependencies installed (`backend/.venv` is used when present, otherwise
the current interpreter) and `npm ci` done in `frontend/`.

## Output

Human summary on stdout, full report in `.test-agent/test-results.json` (`--output` to change):

- `ok` — every selected suite passed (and type-check, if requested).
- `suites.<name>.status` — `passed`, `failed`, `flaky` (outcome differed between `--repeat` runs),
  `no_tests`, or `error` (collection/import error, timeout, missing dependencies).
- `suites.<name>.failures[]` — test id and trimmed failure message.
- `suites.<name>.coverage.totals` and `.files[path]` — line coverage, `uncovered_lines`,
  `partial_lines` (lines with an untaken branch). Feed this file to
  `analyze_changes.py --coverage-from` to see which changed lines are still uncovered.
- `typecheck.status` — `tsc --noEmit` result for the frontend.

## Rules of thumb

- Iterate on the narrowest target; finish with the full affected suites, because new tests can
  break others (shared mocks, module state, timers).
- A test is done only when it passes in the full-suite run and on `--repeat 2`.
- `flaky` is a failure: remove the nondeterminism (real timers, dates, ordering, shared state)
  instead of retrying.
- Vitest does not type-check; always add `--typecheck` when frontend tests changed.
- Never weaken an assertion to make a run green. If the code under test is wrong, report it.

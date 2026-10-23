---
name: validate-test-changes
description: Policy gate for generated test changes — fails if anything other than test files changed, files were deleted or renamed, tests were skipped/focused, or credential-like strings appear; warns on removed assertions and environment, process or network access. Use before finishing any test-writing task.
when_to_use: Final self-check of the agent, and the independent gate the PR workflow applies before publishing a patch.
argument-hint: "[--base <commit>] [--patch <file>]"
allowed-tools: Bash(python3 .claude/skills/validate-test-changes/scripts/check_test_changes.py *)
---

# Validate test changes

Check the working tree against `HEAD`, or an exported patch:

```bash
python3 .claude/skills/validate-test-changes/scripts/check_test_changes.py
python3 .claude/skills/validate-test-changes/scripts/check_test_changes.py --patch tests.patch
```

Exit code 0 means the change set is publishable. The CI workflow runs the same script on the
exported patch in a separate job, so passing it locally is required but the workflow does not
trust the agent's own run.

## Violations (blocking)

| Rule | Why |
| --- | --- |
| `path_not_allowed` | Only `backend/tests/**/*.py`, `frontend/src/**/*.test.ts(x)` and `frontend/src/test/**` may change. Production code, configuration, workflows and agent definitions are off-limits. |
| `file_deleted`, `file_renamed` | Deleting or moving tests hides lost coverage; edit in place and report obsolete files instead. |
| `binary_change` | Tests are text. |
| `file_mode_change` | Only regular files (mode 100644): no symlinks escaping the test folders, no executables. |
| `focused_or_skipped_test`, `skipped_python_test` | `.only`, `.skip`, `.todo`, `xit`, `pytest.mark.skip/xfail`, … silence failures. |
| `possible_secret` | Credential-like values must never be committed or echoed into a PR. |
| `too_many_files`, `patch_too_large` | Keeps a change reviewable (40 files / 4000 added lines). |

## Warnings (reported in the PR, not blocking)

`assertions_removed`, `reads_environment`, `spawns_processes`, `real_network_access` — each
needs a reason in the final summary or a fix (prefer mocks, `monkeypatch`, `vi.stubGlobal`).

Locally the script compares against `HEAD`, so your own uncommitted source edits show up as
`path_not_allowed`; pass `--base` with the commit you started from, or run it after committing them.

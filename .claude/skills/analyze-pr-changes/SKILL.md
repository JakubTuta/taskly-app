---
name: analyze-pr-changes
description: Analyze the files changed in a pull request (or the working tree) and decide which changed backend/frontend code needs new or updated unit tests, using changed-line coverage. Use first in any "add/update tests for these changes" task, or with --all to find untested code across the whole repository.
when_to_use: Start of a PR test run, "write tests for my changes", "which of my changes are untested", "raise coverage".
argument-hint: "[--base <ref>] [--all]"
allowed-tools: Bash(python3 .claude/skills/analyze-pr-changes/scripts/analyze_changes.py *) Read
---

# Analyze PR changes

Turns a diff into a per-file test plan. The script is deterministic, so the agent and the
GitHub workflow make the same first-pass decision; the agent then refines it with judgement.

## Run it

```bash
python3 .claude/skills/analyze-pr-changes/scripts/analyze_changes.py --base <base-ref-or-sha> --run-coverage
```

- `--base` defaults to the merge base with `origin/main`. The head is the working tree (untracked files included).
- `--run-coverage` runs the affected suites with coverage first (through the `run-tests` skill).
  Use `--coverage-from .test-agent/test-results.json` instead to reuse a run you already made.
- `--all` treats every application file as changed: whole-repo coverage mode.
- Output: `.test-agent/analysis.json` (`--output` to change). In CI the workflow has already
  produced it; read it instead of re-running the baseline.

On Windows use `python` instead of `python3`.

## Reading `analysis.json`

| Field | Meaning |
| --- | --- |
| `summary.agent_required` | `false` when nothing testable changed: stop and report `no_changes_needed`. |
| `baseline.<suite>` | Suite status **before** any test changes, with failing test ids and messages. |
| `files[].kind` | `source`, `declarative` (schemas/models/types, omitted from coverage), `test`, `test_support`, `excluded`, `other`. |
| `files[].action` | First-pass recommendation: `write_tests`, `review`, `none`, `skip`. |
| `files[].changed_lines` | Added/modified line numbers on the head side. |
| `files[].coverage.uncovered_changed_lines` | Changed lines no test executes. |
| `files[].coverage.partial_changed_lines` | Changed lines whose branches are not all taken. |
| `files[].tests.existing` / `suggested` | Matching test file(s); `suggested` is where new tests go. |

## Turning hints into decisions

1. **write_tests** – make every uncovered changed line and branch execute *and* assert the
   observable result (return value, HTTP status/body, rendered text, callback arguments,
   cache contents). Extend the existing test file when there is one; otherwise create `suggested`.
2. **review** – coverage is not verification. Read the diff (`git diff <base> -- <file>`) and the
   existing tests. If behaviour changed (values, validation limits, messages, ordering, UI text)
   and no assertion pins the new behaviour, add or adjust assertions. A pure refactor with
   passing tests needs no change; say so in the decision.
3. **declarative** – changed constraints (new field, new limit, new enum value) are tested where
   they are enforced: request validation in router tests, patch rules in validator tests,
   persistence in repository tests. Type-only changes need no tests.
4. **Failing baseline tests** – read the failure next to the diff:
   - the diff intentionally changed that behaviour → update the expectation to the new
     behaviour and mention the diff line that justifies it;
   - the failure looks like a regression or bug in the source → do **not** edit the test to
     match; report it under `suspected_bugs`;
   - a deleted source file breaks an import → remove the obsolete test cases from the file and
     report that the author should delete the file (deleting files is not permitted).
5. **skip / none** – nothing to write. Changed test files are still run during verification.

Re-run the script with `--coverage-from` after writing tests to confirm that
`uncovered_changed_count` dropped to zero (or explain why a line cannot be unit tested).

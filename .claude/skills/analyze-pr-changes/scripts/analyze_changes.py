#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RUN_TESTS = REPO_ROOT / ".claude" / "skills" / "run-tests" / "scripts" / "run_tests.py"
DEFAULT_OUTPUT = REPO_ROOT / ".test-agent" / "analysis.json"

DESCRIPTION = """Analyze the changes of a pull request (or the whole repo) and decide which code needs unit tests.

For every changed file the script records: area (backend/frontend), kind (source,
declarative, test, ...), the changed line numbers, the matching test files, and,
when coverage is available, which *changed* lines no test executes. From that it
derives a recommended action the agent starts from:

    write_tests  changed source lines are not executed by any test
    review       changed lines are executed; check the assertions still describe the new behaviour
    none         the file is a test (it will simply be run)
    skip         not unit-testable here (docs, config, styles, stories, design system, entrypoints)

Classification mirrors the project's own coverage configuration
(backend/pyproject.toml [tool.coverage.run] omit, frontend/vite.config.ts coverage.exclude).

Examples:
    python3 analyze_changes.py --base origin/main --run-coverage
    python3 analyze_changes.py --base "$BASE_SHA" --coverage-from .test-agent/baseline-results.json
    python3 analyze_changes.py --all --run-coverage
"""

RULES = [
    ("backend/tests/", "*", "test", "Backend test file."),
    ("backend/app/main.py", "*", "excluded", "ASGI entrypoint; omitted from coverage in backend/pyproject.toml."),
    ("backend/app/", "__init__.py", "excluded", "Package marker."),
    ("backend/app/", "schemas.py", "declarative", "Pydantic schemas are omitted from coverage; test new constraints through validator/router tests."),
    ("backend/app/", "models.py", "declarative", "ORM models are omitted from coverage; test behaviour through the repository."),
    ("backend/app/", "types.py", "declarative", "Type definitions are omitted from coverage."),
    ("backend/app/", "constants.py", "declarative", "Constants are omitted from coverage."),
    ("backend/app/", "*.py", "source", "Backend application code."),
    ("frontend/src/", "*.test.ts", "test", "Frontend test file."),
    ("frontend/src/", "*.test.tsx", "test", "Frontend test file."),
    ("frontend/src/test/", "*", "test_support", "Shared test setup and fixtures."),
    ("frontend/src/design-system/", "*", "excluded", "Design system is excluded from coverage in vite.config.ts and documented in Storybook."),
    ("frontend/src/main.tsx", "*", "excluded", "Browser entrypoint; excluded from coverage in vite.config.ts."),
    ("frontend/src/", "*.d.ts", "declarative", "Type declarations."),
    ("frontend/src/", "types.ts", "declarative", "Type definitions are excluded from coverage."),
    ("frontend/src/", "*.types.ts", "declarative", "Type definitions are excluded from coverage."),
    ("frontend/src/", "index.ts", "declarative", "Barrel file is excluded from coverage."),
    ("frontend/src/", "constants.ts", "declarative", "Constants are excluded from coverage."),
    ("frontend/src/", "constants.tsx", "declarative", "Constants are excluded from coverage."),
    ("frontend/src/", "*.constants.ts", "declarative", "Constants are excluded from coverage."),
    ("frontend/src/features/todos/api/queryKeys.ts", "*", "declarative", "Query keys are excluded from coverage."),
    ("frontend/src/lib/queryClient.ts", "*", "declarative", "Query client configuration is excluded from coverage."),
    ("frontend/src/", "*.stories.tsx", "excluded", "Storybook story."),
    ("frontend/src/", "*.styles.ts", "excluded", "Styled-components styles."),
    ("frontend/src/", "*.ts", "source", "Frontend application code."),
    ("frontend/src/", "*.tsx", "source", "Frontend application code."),
]

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout


def resolve_base(base: str | None) -> str:
    candidates = [base] if base else ["origin/main", "main"]
    for candidate in candidates:
        try:
            return git("merge-base", candidate, "HEAD").strip()
        except subprocess.CalledProcessError:
            continue
    raise SystemExit(f"Cannot find a merge base for {candidates}; fetch the base branch (git fetch origin main).")


def classify(path: str) -> tuple[str, str]:
    name = path.rsplit("/", 1)[-1]
    for prefix, name_glob, kind, reason in RULES:
        if path.startswith(prefix) and fnmatch.fnmatchcase(name, name_glob):
            return kind, reason
    return "other", "Not application code (docs, config, styles or tooling)."


def area_of(path: str) -> str | None:
    return path.split("/", 1)[0] if path.startswith(("backend/", "frontend/")) else None


def parse_name_status(output: str) -> list[tuple[str, str]]:
    parts = [part for part in output.split("\0") if part]
    changes, index = [], 0
    while index < len(parts):
        status = parts[index]
        if status[0] in "RC":
            changes.append((status[0], parts[index + 2]))
            index += 3
        else:
            changes.append((status[0], parts[index + 1]))
            index += 2
    return changes


def parse_hunks(diff: str) -> tuple[list[int], bool]:
    lines: list[int] = []
    deletions_only = False
    for line in diff.splitlines():
        match = HUNK.match(line)
        if not match:
            continue
        start, count = int(match.group(1)), int(match.group(2) if match.group(2) is not None else 1)
        if count == 0:
            deletions_only = True
        lines.extend(range(start, start + count))
    return lines, deletions_only


def compress(lines: list[int]) -> str:
    ranges: list[list[int]] = []
    for line in sorted(set(lines)):
        if ranges and ranges[-1][1] == line - 1:
            ranges[-1][1] = line
        else:
            ranges.append([line, line])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


def file_line_count(path: str) -> int:
    try:
        return len((REPO_ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def collect_changes(merge_base: str, head: str | None, all_files: bool) -> list[dict]:
    if all_files:
        tracked = git("ls-files", "-z", "backend/app", "frontend/src").split("\0")
        return [
            {"path": path, "status": "A", "lines": list(range(1, file_line_count(path) + 1)), "deletions_only": False}
            for path in tracked if path
        ]
    revs = [merge_base, head] if head else [merge_base]
    changes = parse_name_status(git("diff", "--name-status", "-M", "-z", *revs))
    untracked: set[str] = set()
    if not head:
        untracked = {path for path in git("ls-files", "-o", "--exclude-standard", "-z").split("\0") if path}
        changes += [("A", path) for path in sorted(untracked)]
    result = []
    for status, path in changes:
        if status == "D":
            lines, deletions_only = [], True
        elif path in untracked:
            lines, deletions_only = list(range(1, file_line_count(path) + 1)), False
        else:
            lines, deletions_only = parse_hunks(git("diff", "-U0", *revs, "--", path))
        result.append({"path": path, "status": status, "lines": lines, "deletions_only": deletions_only})
    return result


def test_candidates(path: str) -> list[str]:
    p = Path(path)
    if path.startswith("backend/app/"):
        relative = p.relative_to("backend/app")
        return [(Path("backend/tests") / relative.parent / f"test_{relative.name}").as_posix()]
    if path.startswith("frontend/src/"):
        stem = p.with_suffix("").as_posix()
        return [f"{stem}.test.tsx", f"{stem}.test.ts"] if p.suffix == ".tsx" else [f"{stem}.test.ts", f"{stem}.test.tsx"]
    return []


def run_baseline(suites: list[str], output: Path) -> dict:
    if not suites:
        return {"suites": {}}
    suite = suites[0] if len(suites) == 1 else "all"
    subprocess.run(
        [sys.executable, str(RUN_TESTS), "--suite", suite, "--coverage", "--output", str(output)],
        cwd=REPO_ROOT, check=False,
    )
    return json.loads(output.read_text(encoding="utf-8")) if output.exists() else {"suites": {}}


def decide(entry: dict, coverage_files: dict | None, changed_paths: set[str], whole_repo: bool = False) -> None:
    kind, path = entry["kind"], entry["path"]
    existing = [c for c in test_candidates(path) if (REPO_ROOT / c).exists()]
    entry["tests"] = {
        "existing": existing,
        "suggested": existing[0] if existing else (test_candidates(path) or [None])[0],
        "changed_in_pr": [c for c in test_candidates(path) if c in changed_paths],
    }
    if kind in ("test", "test_support"):
        entry.update(action="none", reason=entry["reason"] + " It will be executed during verification.")
        return
    if kind in ("excluded", "other"):
        entry.update(action="skip")
        return
    if entry["status"] == "D":
        entry.update(action="review" if existing else "skip",
                     reason="Source file deleted; tests that import it must be removed or updated." if existing
                     else "Source file deleted and it has no dedicated tests.")
        return
    if kind == "declarative":
        entry.update(action="skip" if whole_repo else "review")
        return
    file_cov = (coverage_files or {}).get(path)
    if coverage_files is None or file_cov is None:
        entry["coverage"] = {"tracked": False}
        entry.update(action="write_tests" if not existing else "review",
                     reason="No coverage data for this file; " + ("no dedicated test file exists." if not existing
                                                                   else "check existing tests cover the change."))
        return
    changed = set(entry["lines"])
    uncovered = sorted(changed & set(file_cov["uncovered_lines"]))
    partial = sorted(changed & set(file_cov["partial_lines"]))
    entry["coverage"] = {
        "tracked": True,
        "lines_pct": file_cov["lines_pct"],
        "executable_changed_count": len(changed & set(file_cov.get("executable_lines", []))),
        "uncovered_changed_lines": compress(uncovered),
        "partial_changed_lines": compress(partial),
        "uncovered_changed_count": len(uncovered),
        "partial_changed_count": len(partial),
    }
    if uncovered or partial:
        entry.update(action="write_tests", reason=f"{len(uncovered)} changed line(s) never executed and "
                                                  f"{len(partial)} with untested branches.")
    elif whole_repo:
        entry.update(action="skip", reason="Already fully covered.")
    elif entry["deletions_only"] and not changed:
        entry.update(action="review", reason="Lines were only removed; check tests that asserted the removed behaviour.")
    else:
        entry.update(action="review", reason="All changed lines are executed by tests; verify assertions describe "
                                             "the new behaviour (execution is not verification).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", help="Base ref/sha (default: merge-base with origin/main).")
    parser.add_argument("--head", help="Head ref/sha. Default: the working tree, including untracked files.")
    parser.add_argument("--all", action="store_true", help="Treat every application file as changed (coverage mode).")
    coverage = parser.add_mutually_exclusive_group()
    coverage.add_argument("--run-coverage", action="store_true", help="Run affected suites with coverage first.")
    coverage.add_argument("--coverage-from", type=Path, help="Reuse a run_tests.py results file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    merge_base = git("rev-parse", "HEAD").strip() if args.all else resolve_base(args.base)
    changes = collect_changes(merge_base, args.head, args.all)
    changed_paths = {change["path"] for change in changes}

    entries = []
    for change in changes:
        kind, reason = classify(change["path"])
        entries.append({**change, "area": area_of(change["path"]), "kind": kind, "reason": reason})

    affected = sorted({e["area"] for e in entries if e["area"] and e["kind"] not in ("excluded", "other")})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    baseline = None
    if args.run_coverage:
        baseline = run_baseline(affected, args.output.with_name("baseline-results.json"))
    elif args.coverage_from:
        baseline = json.loads(args.coverage_from.read_text(encoding="utf-8"))

    coverage_files = None
    if baseline is not None:
        coverage_files = {}
        for suite in baseline.get("suites", {}).values():
            coverage_files.update(suite.get("coverage", {}).get("files", {}))
    for entry in entries:
        decide(entry, coverage_files, changed_paths, whole_repo=args.all)
        entry["changed_line_count"] = len(entry["lines"])
        entry["changed_lines"] = compress(entry.pop("lines"))
        entry.pop("deletions_only")

    order = {"write_tests": 0, "review": 1, "none": 2, "skip": 3}
    entries.sort(key=lambda e: (order[e["action"]], e["path"]))
    baseline_summary = {
        name: {
            "status": suite["status"],
            "tests": suite["tests"],
            "failures": suite.get("failures", [])[:10],
            "coverage_totals": suite.get("coverage", {}).get("totals"),
        }
        for name, suite in (baseline or {}).get("suites", {}).items()
    }
    failing = [name for name, suite in baseline_summary.items() if suite["status"] != "passed"]
    counts = {action: sum(e["action"] == action for e in entries) for action in order}
    analysis = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "all" if args.all else "diff",
        "base": merge_base,
        "head": args.head or "WORKTREE",
        "summary": {
            "files_changed": len(entries),
            **counts,
            "suites": affected,
            "failing_suites": failing,
            "agent_required": bool(counts["write_tests"] or counts["review"] or failing),
        },
        "baseline": baseline_summary,
        "files": entries,
    }
    args.output.write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    s = analysis["summary"]
    print(f"{s['files_changed']} changed file(s): {s['write_tests']} write_tests, {s['review']} review, "
          f"{s['none']} test files, {s['skip']} skipped. Agent required: {s['agent_required']}.")
    for name, suite in baseline_summary.items():
        print(f"baseline {name}: {suite['status']} ({suite['tests']['passed']} passed, {suite['tests']['failed']} failed)")
    for entry in entries:
        if entry["action"] in ("write_tests", "review"):
            cov = entry.get("coverage", {})
            detail = ""
            if cov.get("uncovered_changed_lines"):
                detail += f" uncovered changed lines: {cov['uncovered_changed_lines']}."
            if cov.get("partial_changed_lines"):
                detail += f" untested branches on lines: {cov['partial_changed_lines']}."
            print(f"- [{entry['action']}] {entry['path']} ({entry['kind']}) → {entry['tests']['suggested']}.{detail}")
    print(f"Analysis: {args.output.relative_to(REPO_ROOT).as_posix() if args.output.is_absolute() else args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND = REPO_ROOT / "backend"
FRONTEND = REPO_ROOT / "frontend"
DEFAULT_OUTPUT_DIR = REPO_ROOT / ".test-agent"

DESCRIPTION = """Run the backend (pytest) and/or frontend (Vitest) unit tests and emit machine-readable results.

Shared by the unit-test agent (run-tests skill) and the GitHub workflow, so both judge test runs
the same way. Test processes get a sanitized environment: only allowlisted variables are passed
through, so credentials in the caller's environment never reach test code.

Examples:
    python3 run_tests.py --suite all --coverage
    python3 run_tests.py backend/tests/features/todos/test_router.py
    python3 run_tests.py --repeat 2 frontend/src/lib/http.test.ts"""

ENV_ALLOWLIST = {
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ",
    "TMPDIR", "TMP", "TEMP", "CI", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "VIRTUAL_ENV",
    "pythonLocation", "RUNNER_TEMP",
    "SYSTEMROOT", "SystemRoot", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "WINDIR",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "NUMBER_OF_PROCESSORS",
}

MAX_FAILURES = 25
MAX_MESSAGE_CHARS = 1500
OUTPUT_TAIL_CHARS = 4000


def sanitized_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in ENV_ALLOWLIST}
    env.update({
        "CI": env.get("CI", "1"),
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TZ": env.get("TZ", "UTC"),
    })
    return env


def python_executable() -> str:
    for candidate in (BACKEND / ".venv" / "bin" / "python", BACKEND / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def node_executable() -> str:
    node = shutil.which("node")
    if not node:
        raise SystemExit("node is not on PATH; install Node.js to run frontend tests.")
    return node


def tail(text: str, limit: int = OUTPUT_TAIL_CHARS) -> str:
    return text if len(text) <= limit else "…" + text[-limit:]


def to_repo_path(path: str | Path) -> str:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = (REPO_ROOT / resolved)
    try:
        return resolved.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def compress_lines(lines: list[int]) -> str:
    """Render [1, 2, 3, 7] as "1-3, 7" so reports stay short."""
    ranges: list[str] = []
    for line in sorted(set(lines)):
        if ranges and int(ranges[-1].split("-")[-1]) == line - 1:
            start = ranges[-1].split("-")[0]
            ranges[-1] = f"{start}-{line}"
        else:
            ranges.append(str(line))
    return ", ".join(ranges)


def parse_junit(path: Path) -> tuple[dict[str, int], list[dict[str, str]], dict[str, str]]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    failures: list[dict[str, str]] = []
    statuses: dict[str, str] = {}
    for suite in suites:
        for case in suite.iter("testcase"):
            test_id = f"{case.get('classname', '')}::{case.get('name', '')}"
            problem = case.find("failure") if case.find("failure") is not None else case.find("error")
            counts["total"] += 1
            if problem is not None:
                counts["failed"] += 1
                statuses[test_id] = "failed"
                message = problem.get("message") or ""
                details = (problem.text or "").strip()
                failures.append({"test": test_id, "message": tail(f"{message}\n{details}".strip(), MAX_MESSAGE_CHARS)})
            elif case.find("skipped") is not None:
                counts["skipped"] += 1
                statuses[test_id] = "skipped"
            else:
                counts["passed"] += 1
                statuses[test_id] = "passed"
    return counts, failures, statuses


def backend_coverage(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    totals = data.get("totals", {})
    files = {}
    for name, info in data.get("files", {}).items():
        summary = info.get("summary", {})
        partial = sorted({branch[0] for branch in info.get("missing_branches", []) if branch and branch[0] > 0})
        files[to_repo_path(BACKEND / name)] = {
            "lines_pct": round(summary.get("percent_covered", 0.0), 2),
            "executable_lines": sorted(set(info.get("executed_lines", [])) | set(info.get("missing_lines", []))),
            "uncovered_lines": sorted(info.get("missing_lines", [])),
            "partial_lines": partial,
        }
    return {
        "totals": {
            "lines_pct": round(totals.get("percent_covered", 0.0), 2),
            "statements": totals.get("num_statements", 0),
            "covered_statements": totals.get("covered_lines", 0),
            "branches": totals.get("num_branches", 0),
            "covered_branches": totals.get("covered_branches", 0),
        },
        "files": files,
    }


def run_backend(targets: list[str], coverage: bool, out_dir: Path, run_index: int, timeout: int) -> dict:
    junit = out_dir / f"backend-junit-{run_index}.xml"
    cov_json = out_dir / f"backend-coverage-{run_index}.json"
    command = [python_executable(), "-m", "pytest", "-q", "-p", "no:cacheprovider", "--color=no", f"--junitxml={junit}"]
    if coverage:
        command += ["--cov=app", f"--cov-report=json:{cov_json}", "--cov-report=term"]
    command += [str(Path(t).relative_to("backend")) if Path(t).parts[:1] == ("backend",) else t for t in targets]
    result = execute(command, BACKEND, timeout)
    if junit.exists():
        counts, failures, statuses = parse_junit(junit)
    else:
        counts, failures, statuses = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}, [], {}
    result.update(tests=counts, failures=failures, statuses=statuses)
    if coverage and cov_json.exists():
        result["coverage"] = backend_coverage(cov_json)
    return result


def istanbul_file_coverage(info: dict) -> dict:
    line_hits: dict[int, int] = {}
    for key, location in info.get("statementMap", {}).items():
        line = location["start"]["line"]
        line_hits[line] = max(line_hits.get(line, 0), info.get("s", {}).get(key, 0))
    uncovered = sorted(line for line, hits in line_hits.items() if hits == 0)
    partial: set[int] = set()
    for key, branch in info.get("branchMap", {}).items():
        counts = info.get("b", {}).get(key, [])
        for index, hits in enumerate(counts):
            if hits == 0:
                locations = branch.get("locations", [])
                start = locations[index].get("start", {}) if index < len(locations) else {}
                partial.add(start.get("line") or branch.get("line") or branch["loc"]["start"]["line"])
    total = len(line_hits)
    pct = 100.0 if total == 0 else round(100.0 * (total - len(uncovered)) / total, 2)
    return {
        "lines_pct": pct,
        "executable_lines": sorted(line_hits),
        "uncovered_lines": uncovered,
        "partial_lines": sorted(partial - set(uncovered)),
    }


def frontend_coverage(final_path: Path, summary_path: Path) -> dict:
    final = json.loads(final_path.read_text(encoding="utf-8"))
    files = {to_repo_path(name): istanbul_file_coverage(info) for name, info in final.items()}
    totals = {}
    if summary_path.exists():
        total = json.loads(summary_path.read_text(encoding="utf-8")).get("total", {})
        totals = {
            "lines_pct": total.get("lines", {}).get("pct", 0),
            "statements_pct": total.get("statements", {}).get("pct", 0),
            "branches_pct": total.get("branches", {}).get("pct", 0),
            "functions_pct": total.get("functions", {}).get("pct", 0),
        }
    return {"totals": totals, "files": files}


def run_frontend(targets: list[str], coverage: bool, out_dir: Path, run_index: int, timeout: int) -> dict:
    report = out_dir / f"frontend-vitest-{run_index}.json"
    cov_dir = out_dir / f"frontend-coverage-{run_index}"
    vitest = FRONTEND / "node_modules" / "vitest" / "vitest.mjs"
    if not vitest.exists():
        return {"status": "error", "exit_code": None, "command": "", "duration_s": 0,
                "output_tail": "frontend/node_modules is missing; run `npm ci` in frontend first.",
                "tests": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}, "failures": [], "statuses": {}}
    command = [node_executable(), str(vitest), "run", "--reporter=default", "--reporter=json", f"--outputFile.json={report}"]
    if coverage:
        command += [
            "--coverage", "--coverage.reporter=json", "--coverage.reporter=json-summary",
            "--coverage.reporter=text-summary", f"--coverage.reportsDirectory={cov_dir}",
        ]
    command += [str(Path(t).relative_to("frontend").as_posix()) if Path(t).parts[:1] == ("frontend",) else t for t in targets]
    result = execute(command, FRONTEND, timeout)
    counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    failures: list[dict[str, str]] = []
    statuses: dict[str, str] = {}
    if report.exists():
        data = json.loads(report.read_text(encoding="utf-8"))
        for file_result in data.get("testResults", []):
            file_name = to_repo_path(file_result.get("name", ""))
            assertions = file_result.get("assertionResults", [])
            if not assertions and file_result.get("status") == "failed":
                counts["total"] += 1
                counts["failed"] += 1
                statuses[file_name] = "failed"
                failures.append({"test": file_name, "message": tail(file_result.get("message", ""), MAX_MESSAGE_CHARS)})
            for assertion in assertions:
                test_id = f"{file_name} > {assertion.get('fullName', assertion.get('title', ''))}"
                status = assertion.get("status")
                counts["total"] += 1
                if status == "passed":
                    counts["passed"] += 1
                    statuses[test_id] = "passed"
                elif status == "failed":
                    counts["failed"] += 1
                    statuses[test_id] = "failed"
                    message = "\n".join(assertion.get("failureMessages", []))
                    failures.append({"test": test_id, "message": tail(message, MAX_MESSAGE_CHARS)})
                else:
                    counts["skipped"] += 1
                    statuses[test_id] = "skipped"
    result.update(tests=counts, failures=failures, statuses=statuses)
    if coverage and (cov_dir / "coverage-final.json").exists():
        result["coverage"] = frontend_coverage(cov_dir / "coverage-final.json", cov_dir / "coverage-summary.json")
    return result


def run_typecheck(timeout: int) -> dict:
    tsc = FRONTEND / "node_modules" / "typescript" / "bin" / "tsc"
    if not tsc.exists():
        return {"status": "error", "output_tail": "typescript is not installed; run `npm ci` in frontend."}
    result = execute([node_executable(), str(tsc), "--noEmit", "-p", "tsconfig.json"], FRONTEND, timeout)
    result["status"] = "passed" if result["exit_code"] == 0 else "failed"
    return result


def execute(command: list[str], cwd: Path, timeout: int) -> dict:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command, cwd=cwd, env=sanitized_env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        exit_code, output = completed.returncode, completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as error:
        exit_code = None
        output = f"Timed out after {timeout}s.\n{(error.stdout or b'')!s}"
    return {
        "command": " ".join(Path(part).name if index < 2 else part for index, part in enumerate(command)),
        "exit_code": exit_code,
        "duration_s": round(time.monotonic() - started, 2),
        "output_tail": tail(output),
    }


def classify(run: dict) -> str:
    tests = run.get("tests", {})
    if run.get("exit_code") is None:
        return "error"
    if tests.get("failed"):
        return "failed"
    if tests.get("total", 0) == 0:
        return "no_tests" if run.get("exit_code") in (0, 5) else "error"
    return "passed" if run.get("exit_code") == 0 else "error"


def merge_runs(runs: list[dict]) -> dict:
    final = dict(runs[-1])
    outcomes: dict[str, set[str]] = {}
    for run in runs:
        for test_id, status in run.get("statuses", {}).items():
            outcomes.setdefault(test_id, set()).add(status)
    final["flaky"] = sorted(test_id for test_id, seen in outcomes.items() if len(seen) > 1)
    final["runs"] = len(runs)
    statuses = [classify(run) for run in runs]
    final["status"] = "flaky" if final["flaky"] else next((s for s in statuses if s != "passed"), "passed")
    final["failures"] = final.get("failures", [])[:MAX_FAILURES]
    final.pop("statuses", None)
    return final


def split_targets(paths: list[str]) -> dict[str, list[str]]:
    targets: dict[str, list[str]] = {"backend": [], "frontend": []}
    for raw in paths:
        path = to_repo_path(raw)
        if path.startswith("backend/"):
            targets["backend"].append(path)
        elif path.startswith("frontend/"):
            targets["frontend"].append(path)
        else:
            raise SystemExit(f"Cannot tell which suite runs {raw!r}; pass paths under backend/ or frontend/.")
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="Test files or directories (repo-relative). Default: whole suites.")
    parser.add_argument("--suite", choices=["backend", "frontend", "all"], default=None)
    parser.add_argument("--coverage", action="store_true", help="Collect coverage (per-file uncovered lines).")
    parser.add_argument("--typecheck", action="store_true", help="Also run `tsc --noEmit` for the frontend.")
    parser.add_argument("--repeat", type=int, default=1, help="Run each suite N times to detect flaky tests.")
    parser.add_argument("--timeout", type=int, default=600, help="Per-run timeout in seconds.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "test-results.json")
    args = parser.parse_args(argv)
    args.output = args.output.resolve()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    targets = split_targets(args.paths)
    if args.suite in (None, "all") and not args.paths:
        suites = ["backend", "frontend"]
    elif args.suite and args.suite != "all":
        suites = [args.suite]
    else:
        suites = [name for name in ("backend", "frontend") if targets[name]]

    out_dir = args.output.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    runners = {"backend": run_backend, "frontend": run_frontend}
    results: dict = {"suites": {}}
    for suite in suites:
        runs = [runners[suite](targets[suite], args.coverage, out_dir, index, args.timeout) for index in range(max(1, args.repeat))]
        results["suites"][suite] = merge_runs(runs)
    if args.typecheck:
        results["typecheck"] = run_typecheck(args.timeout)

    results["ok"] = all(s["status"] == "passed" for s in results["suites"].values()) and (
        results.get("typecheck", {}).get("status", "passed") == "passed"
    )
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")

    for suite, run in results["suites"].items():
        tests = run["tests"]
        line = f"{suite}: {run['status'].upper()} — {tests['passed']} passed, {tests['failed']} failed, {tests['skipped']} skipped"
        if run["runs"] > 1:
            line += f" ({run['runs']} runs)"
        totals = run.get("coverage", {}).get("totals")
        if totals:
            line += f" — line coverage {totals.get('lines_pct')}%"
        print(line)
        for failure in run["failures"]:
            print(f"  ✗ {failure['test']}\n    {failure['message'][:600].replace(chr(10), chr(10) + '    ')}")
        for test_id in run["flaky"]:
            print(f"  ~ flaky: {test_id}")
        if run["status"] == "error":
            print(f"  runner output:\n{run['output_tail']}")
    if "typecheck" in results:
        print(f"typecheck: {results['typecheck']['status'].upper()}")
        if results["typecheck"]["status"] != "passed":
            print(results["typecheck"].get("output_tail", ""))
    print(f"Results: {to_repo_path(args.output)}")
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

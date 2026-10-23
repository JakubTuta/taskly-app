#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

DESCRIPTION = """Policy gate for test changes produced by the unit-test agent.

Checks a unified diff (from --patch, or the working tree against --base) and fails when it:
  * touches anything other than test files,
  * deletes, renames or binary-patches files,
  * adds focused/skipped/expected-failure tests,
  * contains credential-like strings,
  * exceeds size limits.
Weakening signals (removed assertions, environment or process access) are reported as warnings."""

ALLOWED_PATHS = [
    re.compile(r"^backend/tests/(?:[\w.-]+/)*[\w.-]+\.py$"),
    re.compile(r"^frontend/src/(?:[\w.-]+/)*[\w.-]+\.test\.tsx?$"),
    re.compile(r"^frontend/src/test/(?:[\w.-]+/)*[\w.-]+\.tsx?$"),
]

FORBIDDEN_ADDITIONS = [
    ("focused_or_skipped_test", re.compile(r"\b(?:it|test|describe|suite)\s*\.\s*(?:only|skip|todo|fails)\b")),
    ("focused_or_skipped_test", re.compile(r"\b(?:xit|xtest|xdescribe|fit|fdescribe)\s*\(")),
    ("skipped_python_test", re.compile(r"pytest\s*\.\s*(?:mark\s*\.\s*(?:skip|skipif|xfail)|skip\s*\(|xfail\s*\()")),
    ("skipped_python_test", re.compile(r"\bunittest\s*\.\s*(?:skip|skipIf|skipUnless|expectedFailure)\b")),
]

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

WARNING_ADDITIONS = [
    ("reads_environment", re.compile(r"\bos\.environ\b|\bprocess\.env\b|\bgetenv\s*\(")),
    ("spawns_processes", re.compile(r"\bsubprocess\b|\bchild_process\b|\bos\.system\s*\(")),
    ("real_network_access", re.compile(r"https?://(?!localhost|127\.0\.0\.1|testserver|example\.(?:com|org))")),
]

ASSERTION = re.compile(r"\bassert\b|\bexpect\s*\(|\.assert_\w+\(|pytest\.raises\(")

MAX_FILES = 40
MAX_ADDED_LINES = 4000


def git(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and completed.returncode not in (0, 1):
        raise SystemExit(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout


def worktree_patch(base: str) -> str:
    patch = git("diff", "--binary", base)
    for path in filter(None, git("ls-files", "-o", "--exclude-standard", "-z").split("\0")):
        patch += git("diff", "--binary", "--no-index", "--", "/dev/null", path, check=False)
    return patch


def parse_patch(patch: str) -> list[dict]:
    files: list[dict] = []
    current: dict | None = None
    line_number = 0
    in_hunk = False
    for raw in patch.splitlines():
        if raw.startswith("diff --git "):
            current = {
                "path": None, "old_path": None, "status": "modified", "added": [], "removed": [],
                "binary": False, "special_mode": False,
            }
            files.append(current)
            in_hunk = False
            continue
        if current is None:
            continue
        if in_hunk and raw[:1] in ("+", "-", " ", "\\"):
            if raw.startswith("+"):
                current["added"].append((line_number, raw[1:]))
                line_number += 1
            elif raw.startswith("-"):
                current["removed"].append(raw[1:])
            elif raw.startswith(" "):
                line_number += 1
            continue
        if raw.startswith("--- "):
            source = raw[4:].strip()
            current["old_path"] = None if source == "/dev/null" else source.removeprefix("a/")
        elif raw.startswith("+++ "):
            target = raw[4:].strip()
            current["path"] = None if target == "/dev/null" else target.removeprefix("b/")
        elif raw.startswith(("new file mode", "new mode")):
            if raw.startswith("new file mode"):
                current["status"] = "added"
            if not raw.rstrip().endswith("100644"):
                current["special_mode"] = True
        elif raw.startswith("deleted file mode"):
            current["status"] = "deleted"
        elif raw.startswith(("rename from", "rename to", "copy from", "copy to")):
            current["status"] = "renamed"
            if raw.startswith(("rename to", "copy to")):
                current["path"] = raw.split(" ", 2)[2].strip()
        elif raw.startswith(("GIT binary patch", "Binary files")):
            current["binary"] = True
            if current["path"] is None and " and b/" in raw:
                current["path"] = raw.split(" and b/", 1)[1].split(" differ", 1)[0]
        elif raw.startswith("@@"):
            match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", raw)
            line_number = int(match.group(1)) if match else 0
            in_hunk = True
    for entry in files:
        if entry["path"] is None:
            entry["path"] = entry["old_path"]
    return files


def check(patch: str) -> dict:
    files = parse_patch(patch)
    violations: list[dict] = []
    warnings: list[dict] = []

    def flag(bucket: list[dict], rule: str, path: str | None, detail: str, line: int | None = None) -> None:
        bucket.append({"rule": rule, "path": path, "line": line, "detail": detail[:200]})

    if len(files) > MAX_FILES:
        flag(violations, "too_many_files", None, f"{len(files)} files changed (limit {MAX_FILES}).")
    total_added = sum(len(entry["added"]) for entry in files)
    if total_added > MAX_ADDED_LINES:
        flag(violations, "patch_too_large", None, f"{total_added} added lines (limit {MAX_ADDED_LINES}).")

    for entry in files:
        path = entry["path"] or ""
        traversal = any(part in ("", ".", "..") for part in path.split("/"))
        if traversal or not any(pattern.match(path) for pattern in ALLOWED_PATHS):
            flag(violations, "path_not_allowed", path, "Only backend/tests/**, frontend/src/**/*.test.ts(x) and frontend/src/test/** may change.")
        if entry["status"] == "deleted":
            flag(violations, "file_deleted", path, "Existing tests must not be deleted.")
        if entry["status"] == "renamed":
            flag(violations, "file_renamed", path, "Renames are not allowed; edit files in place.")
        if entry["binary"]:
            flag(violations, "binary_change", path, "Binary content is not allowed.")
        if entry["special_mode"] and entry["status"] != "deleted":
            flag(violations, "file_mode_change", path, "Only regular, non-executable files (mode 100644) are allowed.")
        for line_number, text in entry["added"]:
            for rule, pattern in FORBIDDEN_ADDITIONS:
                if pattern.search(text):
                    flag(violations, rule, path, text.strip(), line_number)
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    flag(violations, "possible_secret", path, "Credential-like value found (redacted).", line_number)
            for rule, pattern in WARNING_ADDITIONS:
                if pattern.search(text):
                    flag(warnings, rule, path, text.strip(), line_number)
        removed_asserts = sum(bool(ASSERTION.search(text)) for text in entry["removed"])
        added_asserts = sum(bool(ASSERTION.search(text)) for _, text in entry["added"])
        if removed_asserts > added_asserts:
            flag(warnings, "assertions_removed", path, f"{removed_asserts} assertion line(s) removed, {added_asserts} added.")

    return {
        "ok": not violations,
        "files": [
            {"path": e["path"], "status": e["status"], "added": len(e["added"]), "removed": len(e["removed"])}
            for e in files
        ],
        "violations": violations,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--patch", type=Path, help="Unified diff to check.")
    source.add_argument("--base", default="HEAD", help="Check working-tree changes against this commit (default: HEAD).")
    parser.add_argument("--output", type=Path, help="Write the JSON report here.")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    patch = args.patch.read_text(encoding="utf-8", errors="replace") if args.patch else worktree_patch(args.base)
    report = check(patch)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"{len(report['files'])} file(s) changed: {'PASS' if report['ok'] else 'FAIL'}")
    for item in report["files"]:
        print(f"  {item['status']:<8} {item['path']} (+{item['added']}/-{item['removed']})")
    for violation in report["violations"]:
        location = f"{violation['path']}:{violation['line']}" if violation["line"] else violation["path"] or "patch"
        print(f"✗ {violation['rule']} at {location}: {violation['detail']}")
    for warning in report["warnings"]:
        location = f"{warning['path']}:{warning['line']}" if warning["line"] else warning["path"]
        print(f"! {warning['rule']} at {location}: {warning['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

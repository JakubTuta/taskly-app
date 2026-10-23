import json
import subprocess

import pytest


@pytest.mark.parametrize("path, kind", [
    ("backend/app/features/todos/router.py", "source"),
    ("backend/app/core/config.py", "source"),
    ("backend/app/features/todos/schemas.py", "declarative"),
    ("backend/app/features/todos/models.py", "declarative"),
    ("backend/app/main.py", "excluded"),
    ("backend/app/__init__.py", "excluded"),
    ("backend/tests/features/todos/test_router.py", "test"),
    ("frontend/src/lib/http.ts", "source"),
    ("frontend/src/features/todos/TodosPage.tsx", "source"),
    ("frontend/src/lib/http.test.ts", "test"),
    ("frontend/src/test/todoFixture.ts", "test_support"),
    ("frontend/src/features/todos/types.ts", "declarative"),
    ("frontend/src/design-system/components/Badge/Badge.types.ts", "excluded"),
    ("frontend/src/features/todos/index.ts", "declarative"),
    ("frontend/src/features/todos/api/queryKeys.ts", "declarative"),
    ("frontend/src/design-system/components/Button/Button.tsx", "excluded"),
    ("frontend/src/main.tsx", "excluded"),
    ("frontend/src/styles.css", "other"),
    ("frontend/package.json", "other"),
    ("README.md", "other"),
])
def test_classifies_files_like_the_project_coverage_config(analyze, path, kind):
    assert analyze.classify(path)[0] == kind


def test_parses_name_status_output_including_renames(analyze):
    output = "M\0backend/app/a.py\0R087\0old.py\0frontend/src/new.ts\0A\0x.md\0D\0gone.py\0"
    assert analyze.parse_name_status(output) == [
        ("M", "backend/app/a.py"), ("R", "frontend/src/new.ts"), ("A", "x.md"), ("D", "gone.py"),
    ]


def test_parses_changed_lines_from_zero_context_hunks(analyze):
    diff = "@@ -3 +3 @@\n-a\n+b\n@@ -10,0 +11,3 @@\n+x\n+y\n+z\n@@ -20,2 +23,0 @@\n-gone\n-gone\n"
    assert analyze.parse_hunks(diff) == ([3, 11, 12, 13], True)


def test_compresses_line_numbers_into_ranges(analyze):
    assert analyze.compress([7, 1, 2, 3, 9, 10]) == "1-3, 7, 9-10"
    assert analyze.compress([]) == ""


@pytest.mark.parametrize("path, candidates", [
    ("backend/app/core/config.py", ["backend/tests/core/test_config.py"]),
    ("backend/app/factory.py", ["backend/tests/test_factory.py"]),
    ("frontend/src/lib/http.ts", ["frontend/src/lib/http.test.ts", "frontend/src/lib/http.test.tsx"]),
    ("frontend/src/App.tsx", ["frontend/src/App.test.tsx", "frontend/src/App.test.ts"]),
    ("README.md", []),
])
def test_maps_sources_to_conventional_test_files(analyze, path, candidates):
    assert analyze.test_candidates(path) == candidates


def entry(path, lines, kind="source", status="M"):
    return {"path": path, "status": status, "lines": lines, "deletions_only": False, "kind": kind, "reason": "r"}


def coverage(uncovered=(), partial=(), executable=range(1, 30)):
    return {"lines_pct": 80.0, "uncovered_lines": list(uncovered), "partial_lines": list(partial),
            "executable_lines": list(executable)}


def test_requests_tests_for_uncovered_changed_lines(analyze):
    item = entry("backend/app/x.py", [4, 5, 6])
    analyze.decide(item, {"backend/app/x.py": coverage(uncovered=[5, 20], partial=[6])}, set())
    assert item["action"] == "write_tests"
    assert item["coverage"]["uncovered_changed_lines"] == "5"
    assert item["coverage"]["partial_changed_lines"] == "6"
    assert item["coverage"]["executable_changed_count"] == 3


def test_asks_for_review_when_changed_lines_are_already_executed(analyze):
    item = entry("backend/app/x.py", [4, 5])
    analyze.decide(item, {"backend/app/x.py": coverage(uncovered=[20])}, set())
    assert item["action"] == "review"
    assert "execution is not verification" in item["reason"]


def test_without_coverage_data_requests_tests_only_when_no_test_file_exists(analyze):
    item = entry("backend/app/brand_new.py", [1])
    analyze.decide(item, None, set())
    assert item["action"] == "write_tests"
    assert item["coverage"] == {"tracked": False}


@pytest.mark.parametrize("kind, action", [
    ("test", "none"), ("test_support", "none"), ("excluded", "skip"), ("other", "skip"), ("declarative", "review"),
])
def test_non_source_files_get_fixed_actions(analyze, kind, action):
    item = entry("backend/app/x.py", [1], kind=kind)
    analyze.decide(item, {}, set())
    assert item["action"] == action


def test_whole_repository_mode_skips_fully_covered_and_declarative_files(analyze):
    covered = entry("backend/app/x.py", [1, 2])
    analyze.decide(covered, {"backend/app/x.py": coverage()}, set(), whole_repo=True)
    declarative = entry("backend/app/schemas.py", [1], kind="declarative")
    analyze.decide(declarative, {}, set(), whole_repo=True)
    assert (covered["action"], declarative["action"]) == ("skip", "skip")


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repository(tmp_path, analyze, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "backend/app").mkdir(parents=True)
    (tmp_path / "backend/app/service.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("readme\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    monkeypatch.setattr(analyze, "REPO_ROOT", tmp_path)
    return tmp_path


def test_end_to_end_analysis_of_working_tree_changes(analyze, repository):
    (repository / "backend/app/service.py").write_text(
        "def a():\n    return 1\n\n\ndef b(x):\n    return x * 2\n", encoding="utf-8"
    )
    (repository / "frontend/src").mkdir(parents=True)
    (repository / "frontend/src/util.ts").write_text("export const one = 1\n", encoding="utf-8")
    (repository / "README.md").write_text("changed\n", encoding="utf-8")
    results = repository / "results.json"
    results.write_text(json.dumps({"suites": {"backend": {
        "status": "passed", "tests": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
        "coverage": {"files": {"backend/app/service.py": coverage(uncovered=[6], executable=[1, 2, 5, 6])}},
    }}}), encoding="utf-8")
    output = repository / "analysis.json"
    assert analyze.main(["--base", "main", "--coverage-from", str(results), "--output", str(output)]) == 0
    analysis = json.loads(output.read_text(encoding="utf-8"))
    files = {item["path"]: item for item in analysis["files"]}
    assert files["backend/app/service.py"]["action"] == "write_tests"
    assert files["backend/app/service.py"]["changed_lines"] == "3-6"
    assert files["backend/app/service.py"]["coverage"]["uncovered_changed_lines"] == "6"
    assert files["frontend/src/util.ts"]["action"] == "write_tests"
    assert files["frontend/src/util.ts"]["tests"]["suggested"] == "frontend/src/util.test.ts"
    assert files["README.md"]["action"] == "skip"
    assert analysis["summary"]["agent_required"] is True
    assert analysis["summary"]["suites"] == ["backend", "frontend"]


def test_documentation_only_changes_do_not_require_the_agent(analyze, repository):
    (repository / "README.md").write_text("changed\n", encoding="utf-8")
    output = repository / "analysis.json"
    analyze.main(["--base", "main", "--output", str(output)])
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["agent_required"] is False

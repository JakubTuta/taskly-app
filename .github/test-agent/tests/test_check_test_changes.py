import pytest


def new_file(path, *lines, mode="100644"):
    body = "\n".join(f"+{line}" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\nnew file mode {mode}\nindex 0000000..1111111\n"
        f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}\n"
    )


def modified_file(path, removed, added):
    minus = "\n".join(f"-{line}" for line in removed)
    plus = "\n".join(f"+{line}" for line in added)
    return (
        f"diff --git a/{path} b/{path}\nindex 1111111..2222222 100644\n--- a/{path}\n+++ b/{path}\n"
        f"@@ -1,{len(removed)} +1,{len(added)} @@\n{minus}\n{plus}\n"
    )


def rules(report):
    return [item["rule"] for item in report["violations"]]


@pytest.mark.parametrize("path", [
    "backend/tests/features/todos/test_router.py",
    "backend/tests/api/__init__.py",
    "frontend/src/lib/http.test.ts",
    "frontend/src/features/todos/components/TodoItem.test.tsx",
    "frontend/src/test/queryClientWrapper.tsx",
])
def test_accepts_new_test_files(guard, path):
    report = guard.check(new_file(path, "assert True"))
    assert report["ok"] is True
    assert report["files"] == [{"path": path, "status": "added", "added": 1, "removed": 0}]


@pytest.mark.parametrize("path", [
    "backend/app/features/todos/router.py",
    "frontend/src/lib/http.ts",
    "frontend/package.json",
    ".github/workflows/ci.yml",
    ".claude/agents/unit-test-agent.md",
    "backend/tests/../app/main.py",
    "frontend/src/lib/http.test.ts.bak",
])
def test_rejects_changes_outside_test_files(guard, path):
    assert rules(guard.check(new_file(path, "x = 1"))) == ["path_not_allowed"]


def test_rejects_deleted_test_files(guard):
    patch = (
        "diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\ndeleted file mode 100644\n"
        "--- a/backend/tests/test_a.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-assert True\n"
    )
    assert rules(guard.check(patch)) == ["file_deleted"]


def test_rejects_renames(guard):
    patch = (
        "diff --git a/backend/tests/test_a.py b/backend/tests/test_b.py\nsimilarity index 100%\n"
        "rename from backend/tests/test_a.py\nrename to backend/tests/test_b.py\n"
    )
    report = guard.check(patch)
    assert rules(report) == ["file_renamed"]
    assert report["files"][0]["path"] == "backend/tests/test_b.py"


@pytest.mark.parametrize("mode", ["120000", "100755"])
def test_rejects_symlinks_and_executables(guard, mode):
    assert rules(guard.check(new_file("backend/tests/test_link.py", "../app", mode=mode))) == ["file_mode_change"]


def test_rejects_binary_patches(guard):
    patch = (
        "diff --git a/backend/tests/data.py b/backend/tests/data.py\nnew file mode 100644\n"
        "GIT binary patch\nliteral 3\nKcmZ?wbN&+\n"
    )
    assert "binary_change" in rules(guard.check(patch))


@pytest.mark.parametrize("path, line, rule", [
    ("frontend/src/a.test.ts", "it.only('focuses', () => {})", "focused_or_skipped_test"),
    ("frontend/src/a.test.ts", "describe.skip('skips', () => {})", "focused_or_skipped_test"),
    ("frontend/src/a.test.ts", "test.todo('later')", "focused_or_skipped_test"),
    ("frontend/src/a.test.ts", "xit('disabled', () => {})", "focused_or_skipped_test"),
    ("frontend/src/a.test.ts", "fdescribe('focused', () => {})", "focused_or_skipped_test"),
    ("backend/tests/test_a.py", "@pytest.mark.skip(reason='flaky')", "skipped_python_test"),
    ("backend/tests/test_a.py", "@pytest.mark.xfail", "skipped_python_test"),
    ("backend/tests/test_a.py", "pytest.skip('not now')", "skipped_python_test"),
    ("backend/tests/test_a.py", "@unittest.skip('no')", "skipped_python_test"),
])
def test_rejects_skipped_or_focused_tests(guard, path, line, rule):
    assert rules(guard.check(new_file(path, line))) == [rule]


@pytest.mark.parametrize("secret", [
    "sk-ant-api03-" + "a" * 40,
    "ghp_" + "b" * 36,
    "github_pat_" + "c" * 40,
    "AKIA" + "D" * 16,
    "-----BEGIN OPENSSH PRIVATE KEY-----",
])
def test_rejects_credentials_without_echoing_them(guard, secret):
    report = guard.check(new_file("backend/tests/test_a.py", f"TOKEN = '{secret}'"))
    assert rules(report) == ["possible_secret"]
    assert secret not in report["violations"][0]["detail"]


def test_warns_when_assertions_are_removed(guard):
    patch = modified_file("backend/tests/test_a.py", ["    assert result == 1", "    assert other == 2"], ["    pass"])
    report = guard.check(patch)
    assert report["ok"] is True
    assert [w["rule"] for w in report["warnings"]] == ["assertions_removed"]


@pytest.mark.parametrize("line, rule", [
    ("token = os.environ['TOKEN']", "reads_environment"),
    ("const key = process.env.KEY", "reads_environment"),
    ("subprocess.run(['ls'])", "spawns_processes"),
    ("fetch('https://api.example.net/x')", "real_network_access"),
])
def test_warns_on_environment_process_and_network_access(guard, line, rule):
    report = guard.check(new_file("frontend/src/a.test.ts", line))
    assert report["ok"] is True
    assert [w["rule"] for w in report["warnings"]] == [rule]


def test_hunk_lines_that_look_like_headers_are_content(guard):
    patch = modified_file("backend/tests/test_a.py", ["-- old"], ["++ new", "assert True"])
    report = guard.check(patch)
    assert report["ok"] is True
    assert report["files"] == [{"path": "backend/tests/test_a.py", "status": "modified", "added": 2, "removed": 1}]


def test_limits_patch_size(guard, monkeypatch):
    monkeypatch.setattr(guard, "MAX_ADDED_LINES", 3)
    assert "patch_too_large" in rules(guard.check(new_file("backend/tests/test_a.py", *["x = 1"] * 4)))


def test_limits_file_count(guard, monkeypatch):
    monkeypatch.setattr(guard, "MAX_FILES", 1)
    patch = new_file("backend/tests/test_a.py", "x = 1") + new_file("backend/tests/test_b.py", "x = 1")
    assert "too_many_files" in rules(guard.check(patch))


def test_empty_patch_is_publishable(guard):
    assert guard.check("") == {"ok": True, "files": [], "violations": [], "warnings": []}


def test_cli_writes_report_and_fails_on_violations(guard, tmp_path, capsys):
    patch = tmp_path / "tests.patch"
    patch.write_text(new_file("backend/app/x.py", "x = 1"), encoding="utf-8")
    output = tmp_path / "guard.json"
    assert guard.main(["--patch", str(patch), "--output", str(output)]) == 1
    assert '"path_not_allowed"' in output.read_text(encoding="utf-8")
    assert "FAIL" in capsys.readouterr().out

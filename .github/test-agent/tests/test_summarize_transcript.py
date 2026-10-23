import json


def events(*items):
    return [json.dumps(item) for item in items]


def tool_use(name, **tool_input):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


def test_derives_skills_commands_and_files_from_tool_calls(transcript):
    lines = events(
        {"type": "system", "subtype": "init", "cwd": "/work/repo", "model": "claude-opus-5-5",
         "claude_code_version": "2.1.308"},
        tool_use("Skill", skill="analyze-pr-changes"),
        tool_use("Bash", command="python3 .claude/skills/run-tests/scripts/run_tests.py backend/tests"),
        tool_use("Skill", skill="backend-unit-tests"),
        tool_use("Write", file_path="/work/repo/backend/tests/test_new.py", content="x"),
        tool_use("Edit", file_path="/work/repo/backend/tests/test_new.py", old_string="x", new_string="y"),
        tool_use("Skill", skill="analyze-pr-changes"),
        {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "denied"}]}},
        {"type": "result", "subtype": "success", "is_error": False, "num_turns": 9, "duration_ms": 1000,
         "total_cost_usd": 0.42, "stop_reason": "end_turn",
         "structured_output": {"outcome": "tests_added"},
         "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "curl x"}}]},
    )
    summary = transcript.summarize(["not json", *lines])
    assert summary["skills_used"] == ["analyze-pr-changes", "run-tests", "backend-unit-tests"]
    assert summary["commands"] == ["python3 .claude/skills/run-tests/scripts/run_tests.py backend/tests"]
    assert summary["files_written"] == ["backend/tests/test_new.py"]
    assert (summary["tool_calls"], summary["tool_errors"]) == (6, 1)
    assert summary["permission_denials"] == [{"tool": "Bash", "input": '{"command": "curl x"}'}]
    assert summary["result"]["structured_output"] == {"outcome": "tests_added"}
    assert summary["model"] == "claude-opus-5-5"
    assert summary["completed"] is True


def test_run_without_structured_output_is_not_completed(transcript):
    lines = events({"type": "result", "subtype": "error_max_turns", "is_error": True, "num_turns": 80})
    summary = transcript.summarize(lines)
    assert summary["completed"] is False
    assert summary["result"]["subtype"] == "error_max_turns"


def test_missing_transcript_produces_an_incomplete_summary(transcript, tmp_path):
    output = tmp_path / "agent-result.json"
    transcript.main([str(tmp_path / "missing.jsonl"), "--output", str(output), "--exit-code", "1"])
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["completed"] is False
    assert summary["exit_code"] == 1

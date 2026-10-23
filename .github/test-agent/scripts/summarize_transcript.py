#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DESCRIPTION = """Summarize a Claude Code stream-json transcript into agent-result.json.

The summary is derived from the recorded tool calls rather than from the agent's own claims:
which skills it invoked, which commands it ran, which files it wrote, permission denials,
turns, cost and the schema-validated structured output."""

MAX_COMMANDS = 60
MAX_COMMAND_CHARS = 240


def relative(path: str, cwd: str | None) -> str:
    normalized = path.replace("\\", "/")
    if cwd:
        prefix = cwd.replace("\\", "/").rstrip("/") + "/"
        if normalized.lower().startswith(prefix.lower()):
            return normalized[len(prefix):]
    return normalized


def summarize(lines: list[str]) -> dict:
    summary: dict = {
        "model": None,
        "claude_code_version": None,
        "skills_used": [],
        "commands": [],
        "files_written": [],
        "tool_calls": 0,
        "tool_errors": 0,
        "permission_denials": [],
        "result": None,
    }
    cwd = None
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            cwd = event.get("cwd")
            summary["model"] = event.get("model")
            summary["claude_code_version"] = event.get("claude_code_version")
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                summary["tool_calls"] += 1
                name, tool_input = block.get("name"), block.get("input") or {}
                if name == "Skill":
                    skill = tool_input.get("skill") or tool_input.get("command")
                    if skill and skill not in summary["skills_used"]:
                        summary["skills_used"].append(skill)
                elif name == "Bash" and len(summary["commands"]) < MAX_COMMANDS:
                    summary["commands"].append(str(tool_input.get("command", ""))[:MAX_COMMAND_CHARS])
                elif name in ("Edit", "Write") and tool_input.get("file_path"):
                    path = relative(tool_input["file_path"], cwd)
                    if path not in summary["files_written"]:
                        summary["files_written"].append(path)
        elif kind == "user":
            content = event.get("message", {}).get("content")
            if isinstance(content, list):
                summary["tool_errors"] += sum(
                    1 for block in content if block.get("type") == "tool_result" and block.get("is_error")
                )
        elif kind == "result":
            summary["result"] = {
                "subtype": event.get("subtype"),
                "is_error": event.get("is_error"),
                "stop_reason": event.get("stop_reason"),
                "num_turns": event.get("num_turns"),
                "duration_ms": event.get("duration_ms"),
                "total_cost_usd": event.get("total_cost_usd"),
                "structured_output": event.get("structured_output"),
            }
            summary["permission_denials"] = [
                {"tool": denial.get("tool_name"), "input": json.dumps(denial.get("tool_input"))[:200]}
                for denial in event.get("permission_denials") or []
            ]
    summary["completed"] = bool(
        summary["result"] and not summary["result"]["is_error"] and summary["result"]["structured_output"]
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, default=None, help="Exit code of the claude process.")
    args = parser.parse_args(argv)

    lines = args.transcript.read_text(encoding="utf-8", errors="replace").splitlines() if args.transcript.exists() else []
    summary = summarize(lines)
    summary["exit_code"] = args.exit_code
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    result = summary["result"] or {}
    print(f"completed={summary['completed']} turns={result.get('num_turns')} cost={result.get('total_cost_usd')} "
          f"skills={','.join(summary['skills_used'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

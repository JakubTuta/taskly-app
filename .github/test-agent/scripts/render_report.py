#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

DESCRIPTION = """Render the unit-test agent's pull request comment from the workflow artifacts.

Every number comes from deterministic steps (analysis, policy gate, independent test run).
Text written by the agent is treated as untrusted: it is escaped, stripped of links and
mentions, redacted for credential-like values and length-limited before it reaches the PR."""

MARKER = "<!-- unit-test-agent-report -->"
MAX_COMMENT_CHARS = 60000
SECRET = re.compile(
    r"sk-ant-[A-Za-z0-9_\-]{8,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bAKIA[0-9A-Z]{16}\b"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bxox[abprs]-[A-Za-z0-9-]{10,}"
)
SAFE_PATH = re.compile(r"^[A-Za-z0-9_./\[\]-]{1,200}$")
DECISION_LABELS = {
    "created_tests": "🆕 created tests",
    "updated_tests": "✏️ updated tests",
    "no_change": "➖ no change",
    "skipped": "⏭️ skipped",
}
SUITE_ICONS = {"passed": "✅", "failed": "❌", "flaky": "⚠️", "error": "❌", "no_tests": "➖"}


def load(path: Path | None) -> dict | None:
    if not path or not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def plain(value: object, limit: int = 400) -> str:
    text = SECRET.sub("[redacted]", str(value or ""))
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"(?i)\b(?:https?|ftp|data|javascript)://?\S*", "[link removed]", text)
    text = html.escape(text, quote=False)
    text = re.sub(r"([\\`*_{}\[\]()#+!|~>])", r"\\\1", text)
    text = text.replace("@", "@​")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def code(value: object, limit: int = 60) -> str:
    text = str(value or "")
    return f"`{text}`" if re.match(r"^[\w.:@/-]{1,%d}$" % limit, text) else plain(text, limit)


def path_cell(value: object) -> str:
    text = str(value or "")
    return f"`{text}`" if SAFE_PATH.match(text) else plain(text, 120)


def code_block(lines: list[str], language: str = "") -> str:
    body = SECRET.sub("[redacted]", "\n".join(lines))
    fence = "````"
    while fence in body:
        fence += "`"
    return f"{fence}{language}\n{body}\n{fence}"


def pct(value: object) -> str:
    return "–" if value is None else f"{float(value):.0f}%"


def changed_line_totals(analysis: dict | None) -> tuple[int, int]:
    executable = uncovered = 0
    for entry in (analysis or {}).get("files", []):
        coverage = entry.get("coverage") or {}
        if entry.get("kind") == "source" and coverage.get("tracked"):
            executable += coverage.get("executable_changed_count", 0)
            uncovered += coverage.get("uncovered_changed_count", 0)
    return executable, uncovered


def headline(ctx: dict) -> str:
    analysis, agent, guard, verify, publish = (ctx[k] for k in ("analysis", "agent", "guard", "verify", "publish"))
    if analysis is None:
        return "⚠️ **The change analysis failed**, so the agent did not run. Check the workflow logs."
    if not analysis["summary"]["agent_required"]:
        return "ℹ️ **No unit-testable code changed** — nothing for the agent to do."
    if not agent or not agent.get("completed"):
        reason = "it stopped before returning a result"
        result = (agent or {}).get("result") or {}
        if result.get("subtype") and result.get("subtype") != "success":
            reason = f"it stopped with {code(result['subtype'], 40)}"
        return f"⚠️ **The agent did not finish** ({reason}). Nothing was published."
    if guard and not guard.get("ok"):
        return "❌ **The policy gate rejected the generated changes.** Nothing was published."
    files = (guard or {}).get("files") or []
    outcome = ((agent.get("result") or {}).get("structured_output") or {}).get("outcome")
    if outcome == "blocked":
        return "⚠️ **The agent reported that it was blocked** — see its summary below. Nothing was published."
    if not files and outcome in ("tests_added", "tests_updated", "tests_added_and_updated"):
        return f"⚠️ **The agent reported `{outcome}` but produced no file changes.** Nothing was published."
    if not files:
        if verify and not verify.get("ok"):
            return "⚠️ **No test changes were proposed, but the test suites are failing.** See the details below."
        return "✅ **No test changes needed** — the agent judged the existing tests sufficient."
    if not verify or not verify.get("ok"):
        return "❌ **The generated tests failed independent verification.** Nothing was published."
    count = len(files)
    status = (publish or {}).get("status")
    if status == "committed":
        commit = plain((publish or {}).get("commit", ""), 40)[:12]
        return f"✅ **{count} test file(s) created or updated, verified and committed** in {commit}."
    if status == "stale":
        return (f"⚠️ **{count} verified test file(s) were not committed** because the branch moved while the agent "
                "ran. The new commit gets its own run.")
    if status == "push_failed":
        return f"⚠️ **{count} verified test file(s) could not be pushed** to the branch; apply the patch below."
    return f"✅ **{count} test file(s) generated and verified.** Apply the patch below to keep them."


def overview(ctx: dict) -> list[str]:
    analysis, agent, guard, verify = (ctx[k] for k in ("analysis", "agent", "guard", "verify"))
    rows: list[tuple[str, str]] = []
    if analysis:
        s = analysis["summary"]
        rows.append(("Changed files", f"{s['files_changed']} — {s['write_tests']} needed tests, {s['review']} to review, "
                                      f"{s['none']} test files, {s['skip']} not unit-testable"))
    structured = ((agent or {}).get("result") or {}).get("structured_output") or {}
    if structured.get("outcome"):
        rows.append(("Agent outcome", f"{code(structured['outcome'], 40)}"))
    if verify:
        parts = []
        for name, suite in verify.get("suites", {}).items():
            tests = suite.get("tests", {})
            parts.append(f"{SUITE_ICONS.get(suite.get('status'), '❔')} {name} {tests.get('passed', 0)}/{tests.get('total', 0)}")
        runs = max((suite.get("runs", 1) for suite in verify.get("suites", {}).values()), default=1)
        typecheck = verify.get("typecheck", {}).get("status")
        if typecheck:
            parts.append(f"{'✅' if typecheck == 'passed' else '❌'} types")
        fmt = ctx.get("format_status")
        if fmt and fmt != "skipped":
            parts.append(f"{'✅' if fmt == 'passed' else '❌'} formatting")
        rows.append(("Verification", " · ".join(parts) + f" ({runs} run{'s' if runs > 1 else ''}, clean job)"))
    before = changed_line_totals(analysis)
    after = changed_line_totals(ctx.get("analysis_after"))
    if before[0]:
        text = f"{before[0] - before[1]}/{before[0]} before"
        if ctx.get("analysis_after"):
            text += f" → **{after[0] - after[1]}/{after[0]} after**"
        rows.append(("Changed executable lines covered", text))
    if guard:
        warnings = len(guard.get("warnings", []))
        rows.append(("Policy gate", ("✅ passed" if guard.get("ok") else f"❌ {len(guard.get('violations', []))} violation(s)")
                     + (f", {warnings} warning(s)" if warnings else "")))
    if not rows:
        return []
    return ["| | |", "| --- | --- |", *[f"| **{label}** | {value} |" for label, value in rows], ""]


def decisions_section(ctx: dict) -> list[str]:
    agent, analysis = ctx["agent"], ctx["analysis"]
    structured = ((agent or {}).get("result") or {}).get("structured_output") or {}
    decisions = structured.get("decisions") or []
    expected = [e["path"] for e in (analysis or {}).get("files", []) if e.get("action") in ("write_tests", "review")]
    if not decisions and not expected:
        return []
    lines = ["### Agent decisions", "", "| Changed file | Analysis | Decision | Test files | Reason |",
             "| --- | --- | --- | --- | --- |"]
    actions = {e["path"]: e.get("action") for e in (analysis or {}).get("files", [])}
    seen = set()
    for decision in decisions[:60]:
        file = str(decision.get("file", ""))
        seen.add(file)
        tests = ", ".join(path_cell(t) for t in (decision.get("test_files") or [])[:6]) or "–"
        lines.append(f"| {path_cell(file)} | {actions.get(file, '–')} | "
                     f"{DECISION_LABELS.get(decision.get('decision'), plain(decision.get('decision'), 30))} | "
                     f"{tests} | {plain(decision.get('reason'), 300)} |")
    if agent and agent.get("completed"):
        for path in expected:
            if path not in seen:
                lines.append(f"| {path_cell(path)} | {actions.get(path)} | ⚠️ not addressed | – | "
                             "The agent returned no decision for this file. |")
    return [*lines, ""]


def coverage_section(ctx: dict) -> list[str]:
    before = {e["path"]: e for e in (ctx["analysis"] or {}).get("files", []) if (e.get("coverage") or {}).get("tracked")}
    if not before:
        return []
    after = {e["path"]: e for e in (ctx.get("analysis_after") or {}).get("files", [])}
    lines = ["### Coverage of changed code", "",
             "| File | File coverage before → after | Uncovered changed lines before | after |",
             "| --- | --- | --- | --- |"]
    for path, entry in sorted(before.items()):
        old = entry["coverage"]
        new = (after.get(path) or {}).get("coverage") or {}
        lines.append(
            f"| {path_cell(path)} | {pct(old.get('lines_pct'))} → {pct(new.get('lines_pct'))} | "
            f"{old.get('uncovered_changed_lines') or 'none'} | "
            f"{(new.get('uncovered_changed_lines') or 'none') if new else '–'} |"
        )
    return [*lines, ""]


def grouped_failures(failures: list[dict], limit: int = 6) -> list[str]:
    groups: dict[str, list[str]] = {}
    for failure in failures:
        message = "\n    ".join(str(failure.get("message", "")).strip().splitlines()[:4])[:400]
        groups.setdefault(message, []).append(str(failure.get("test", "")))
    lines = []
    for message, tests in list(groups.items())[:limit]:
        more = f" (+{len(tests) - 1} more with the same error)" if len(tests) > 1 else ""
        lines.append(f"{tests[0]}{more}\n    {message}")
    return lines


def verification_section(ctx: dict) -> list[str]:
    verify = ctx["verify"]
    if not verify:
        return []
    lines = ["### Test execution", "",
             "Independent re-run in a clean job, after applying the agent's patch to the PR head.", "",
             "| Suite | Status | Passed | Failed | Skipped | Runs | Line coverage |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    failures: list[str] = []
    for name, suite in verify.get("suites", {}).items():
        tests = suite.get("tests", {})
        totals = (suite.get("coverage") or {}).get("totals") or {}
        lines.append(f"| {name} | {SUITE_ICONS.get(suite.get('status'), '❔')} {plain(suite.get('status'), 20)} | "
                     f"{tests.get('passed', 0)} | {tests.get('failed', 0)} | {tests.get('skipped', 0)} | "
                     f"{suite.get('runs', 1)} | {pct(totals.get('lines_pct'))} |")
        failures += grouped_failures(suite.get("failures", []))
        for test in suite.get("flaky", [])[:10]:
            failures.append(f"FLAKY {test}")
    typecheck = verify.get("typecheck")
    if typecheck:
        lines.append(f"| typecheck | {'✅' if typecheck.get('status') == 'passed' else '❌'} {typecheck.get('status')} "
                     "| – | – | – | 1 | – |")
        if typecheck.get("status") != "passed":
            failures.append("tsc --noEmit\n" + str(typecheck.get("output_tail", ""))[-1500:])
    lines.append("")
    if failures:
        lines += ["<details><summary>Failures</summary>", "", code_block(failures, "text"), "", "</details>", ""]
    return lines


def gate_section(ctx: dict) -> list[str]:
    guard = ctx["guard"]
    if not guard or (guard.get("ok") and not guard.get("warnings")):
        return []
    lines = ["### Policy gate", ""]
    for item in guard.get("violations", [])[:20]:
        lines.append(f"- ❌ {code(item.get('rule'), 40)} {path_cell(item.get('path'))}: {plain(item.get('detail'), 200)}")
    for item in guard.get("warnings", [])[:20]:
        lines.append(f"- ⚠️ {code(item.get('rule'), 40)} {path_cell(item.get('path'))}: {plain(item.get('detail'), 200)}")
    return [*lines, ""]


def bugs_section(ctx: dict) -> list[str]:
    structured = (((ctx["agent"] or {}).get("result") or {}).get("structured_output")) or {}
    bugs = structured.get("suspected_bugs") or []
    if not bugs:
        return []
    lines = ["### Suspected bugs reported by the agent", "",
             "The agent does not change production code; these need a human decision.", ""]
    for bug in bugs[:20]:
        lines.append(f"- {path_cell(bug.get('file'))}: {plain(bug.get('description'), 500)}")
    return [*lines, ""]


def baseline_section(ctx: dict) -> list[str]:
    baseline = (ctx["analysis"] or {}).get("baseline") or {}
    failing = {name: suite for name, suite in baseline.items() if suite.get("status") != "passed"}
    if not failing:
        return []
    lines = ["### Tests failing before the agent ran", ""]
    for name, suite in failing.items():
        tests = suite.get("tests", {})
        lines.append(f"- {name}: {plain(suite.get('status'), 20)} ({tests.get('failed', 0)} failed)")
        for failure in suite.get("failures", [])[:5]:
            lines.append(f"  - {path_cell(failure.get('test')) if SAFE_PATH.match(str(failure.get('test'))) else plain(failure.get('test'), 160)}")
    return [*lines, ""]


def run_details(ctx: dict) -> list[str]:
    agent = ctx["agent"]
    if not agent:
        return []
    result = agent.get("result") or {}
    structured = result.get("structured_output") or {}
    lines = ["<details><summary>Agent run details</summary>", ""]
    if structured.get("summary"):
        lines += [f"**Summary:** {plain(structured['summary'], 1200)}", ""]
    meta = []
    if agent.get("model"):
        meta.append(f"model {code(agent['model'], 60)}")
    if agent.get("claude_code_version"):
        meta.append(f"Claude Code {plain(agent['claude_code_version'], 20)}")
    if result.get("num_turns") is not None:
        meta.append(f"{result['num_turns']} turns")
    if result.get("duration_ms"):
        meta.append(f"{result['duration_ms'] / 60000:.1f} min")
    if result.get("total_cost_usd") is not None:
        meta.append(f"${result['total_cost_usd']:.2f}")
    if meta:
        lines += ["**Run:** " + " · ".join(meta), ""]
    skills = agent.get("skills_used") or []
    lines += ["**Skills used** (from the transcript): " + (" → ".join(code(s, 60) for s in skills) or "none"), ""]
    if agent.get("files_written"):
        lines += ["**Files written:** " + ", ".join(path_cell(f) for f in agent["files_written"][:30]), ""]
    if agent.get("permission_denials"):
        lines += [f"**Permission denials:** {len(agent['permission_denials'])} (blocked by the CI permission policy)", ""]
    if agent.get("commands"):
        lines += [f"**Commands executed** ({len(agent['commands'])}):", "", code_block(agent["commands"], "sh"), ""]
    lines.append("</details>")
    return [*lines, ""]


def patch_section(ctx: dict) -> list[str]:
    publish, patch = ctx.get("publish") or {}, ctx.get("patch")
    if not patch or publish.get("status") == "committed" or not (ctx["verify"] or {}).get("ok"):
        return []
    if not (ctx["guard"] or {}).get("ok"):
        return []
    body = patch if len(patch) < 30000 else patch[:30000] + "\n… (truncated; download the tests-patch artifact)"
    return ["<details><summary>Generated patch</summary>", "",
            "Apply with `git apply tests.patch` (also available as the workflow artifact).", "",
            code_block(body.splitlines(), "diff"), "", "</details>", ""]


def render(ctx: dict) -> str:
    sections = [
        [MARKER, "## 🧪 Unit test agent", "", headline(ctx), ""],
        overview(ctx),
        decisions_section(ctx),
        coverage_section(ctx),
        verification_section(ctx),
        baseline_section(ctx),
        gate_section(ctx),
        bugs_section(ctx),
        run_details(ctx),
        patch_section(ctx),
    ]
    footer = []
    if ctx.get("run_url") and re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/actions/runs/\d+(/attempts/\d+)?$", ctx["run_url"]):
        footer.append(f"[Workflow run]({ctx['run_url']}) — artifacts contain the analysis, agent transcript, patch and test reports.")
    footer.append("Add the `skip-test-agent` label to opt a pull request out.")
    sections.append(["---", "<sub>" + " ".join(footer) + "</sub>"])
    text = "\n".join(line for section in sections for line in section)
    if len(text) > MAX_COMMENT_CHARS:
        text = text[: MAX_COMMENT_CHARS - 200] + "\n\n… report truncated; see the workflow artifacts.\n"
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    for name in ("analysis", "analysis-after", "agent", "guard", "verify", "publish"):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--patch", type=Path)
    parser.add_argument("--format-status", choices=["passed", "failed", "skipped"], default="skipped")
    parser.add_argument("--run-url")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    ctx = {
        "analysis": load(args.analysis),
        "analysis_after": load(args.analysis_after),
        "agent": load(args.agent),
        "guard": load(args.guard),
        "verify": load(args.verify),
        "publish": load(args.publish),
        "patch": args.patch.read_text(encoding="utf-8", errors="replace") if args.patch and args.patch.exists() else None,
        "format_status": args.format_status,
        "run_url": args.run_url,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(ctx), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = {
    "analyze_changes": REPO_ROOT / ".claude/skills/analyze-pr-changes/scripts/analyze_changes.py",
    "run_tests": REPO_ROOT / ".claude/skills/run-tests/scripts/run_tests.py",
    "check_test_changes": REPO_ROOT / ".claude/skills/validate-test-changes/scripts/check_test_changes.py",
    "summarize_transcript": REPO_ROOT / ".github/test-agent/scripts/summarize_transcript.py",
    "render_report": REPO_ROOT / ".github/test-agent/scripts/render_report.py",
}


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"agent_tooling_{name}", SCRIPTS[name])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def analyze():
    return load_script("analyze_changes")


@pytest.fixture(scope="session")
def runner():
    return load_script("run_tests")


@pytest.fixture(scope="session")
def guard():
    return load_script("check_test_changes")


@pytest.fixture(scope="session")
def transcript():
    return load_script("summarize_transcript")


@pytest.fixture(scope="session")
def report():
    return load_script("render_report")

Run your pull request workflow on the checked-out working tree.

- Base commit: {{BASE_SHA}}. Use `--base {{BASE_SHA}}` whenever a command needs the base.
- Head commit: {{HEAD_SHA}} (already checked out).
- The deterministic pre-analysis is at `.test-agent/analysis.json`. It already contains the
  baseline test results and changed-line coverage, so read it instead of re-running the baseline.

Work through every file the analysis marks `write_tests` or `review` and every failing baseline
test. Write or update unit tests where your judgement says they are needed, verify them with the
run-tests skill (affected suites, `--coverage --repeat 2`, plus `--typecheck` when frontend tests
changed), re-run the analysis with `--coverage-from .test-agent/test-results.json`, and finish
with the validate-test-changes skill.

This is an unattended CI run: there is no network access and no one to answer questions, so do
not ask for confirmation. Keep the change focused on this pull request. End with the structured
result.

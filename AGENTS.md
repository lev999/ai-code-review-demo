# Demo engineering rules

<!-- SYNTHETIC AGENT RULES — written by the demo executor; no real person supplied or approved them. -->

These standing rules are synthetic. This file records the initial simulated product rules and the workflow for this independent task-board demonstration. Use original sample data only. Do not add employer data, private notes, credentials, host paths, or unverified results.

## SIMULATED FEATURE REQUEST

The exact, immutable request is in [specs/synthetic-feature-request.md](specs/synthetic-feature-request.md). Its original label is SYNTHETIC FEATURE REQUEST. For this project it is also the SIMULATED FEATURE REQUEST. The demo executor wrote it; do not attribute it to the author or another person. Do not change its text after feature implementation starts. Record any needed correction as a new synthetic version with its own provenance.

## SIMULATED PRODUCT RULES

These are the initial rules for the task-board feature. Each ID is stable. A later change must name the IDs it changes.

- RULE-BOARD-001: The board has two lists named To do and Done.
- RULE-BOARD-002: A fresh demo database starts with task-1, Write one small test, and task-2, Check the board state, in To do. Done starts empty.
- RULE-SELECT-001: Move selected is disabled when no task is selected.
- RULE-SELECT-002: The initial behavior supports moving exactly one selected task from To do. The button is enabled only when exactly one task in To do is selected. A request to move two selected tasks together changes this rule and needs a judgment decision.
- RULE-MOVE-001: Moving the selected task moves only that task to Done. Every other task stays in its current list.
- RULE-SAVE-001: Save each move in SQLite. After reload, both lists show the saved state read from SQLite.
- RULE-API-001: GET /api/tasks returns all rows in this shape: {"lists":{"todo":[{"id":"task-1","title":"Write one small test"},{"id":"task-2","title":"Check the board state"}],"done":[]}}.
- RULE-API-002: POST /api/tasks/{task_id}/move-to-done moves one task in one SQLite transaction and returns {"id":"task-1","list":"done"} with status 200.
- RULE-API-003: Return 404 for an unknown task ID and 409 when the task is not in To do. A request must not move other rows.
- RULE-DATA-001: Store a stable text ID as the primary key, a text title, a list_name value constrained to todo or done, and an integer position. Seed only an empty database. Use a fresh temporary SQLite file in tests.
- RULE-TEST-001: Keep the component, API, and browser persistence checks as separate required tests with stable IDs and trusted hashes. The browser check reads both lists after reload and checks the SQLite rows.

### SIMULATED PRODUCT RULES: H8 routine example

This separate note defines the planned, behavior-preserving title-normalization example. It does not change the simulated feature request, the original rule IDs, or `RULE-TEST-001`.

- The H8 patch may move the existing `row["title"].strip()` behavior into `api/task_text.py` as `normalize_title(value)`, which returns `value.strip()`.
- The patch may add the focused unit test `api/tests/test_task_text.py` for this helper.
- The new test is additional. Keep every original bootstrap, component, API, and browser check unchanged. Keep their paths, IDs, hashes, and commands unchanged, and continue to run all of them. The new test must not replace or weaken an original check.

## Feature-to-spec workflow

1. Read the exact synthetic request and these rules before changing application code.
2. Keep the behavior in [specs/move-one-task.feature](specs/move-one-task.feature). Give each scenario the rule IDs it checks. Link each scenario to the planned executable check in a comment.
3. Add or update executable checks for the Gherkin scenarios before implementation. Keep the rule IDs in the test names or comments so a reader can trace each rule to its check.
4. Preserve the original request and this initial rule set. A rule change must state the old and new behavior and list each changed rule ID in the pull request.
5. Keep the existing infrastructure smoke fixtures as evidence. Do not treat them as the complete two-list feature suite.

## Red-then-green workflow

- Set up dependencies with make setup. Run make verify as the stable command for the component, API, and real-browser checks.
- Add the tests before feature code. Run the checks on the test-only revision and save the real failing result with its exact revision. The expected behavior failure is evidence only when setup succeeded and the assertion failed.
- Implement the smallest change that meets the rules. Run the same checks again and save the real passing result with its exact revision. A setup error or missing test is not a pass.
- Keep separate evidence for local and GitHub Actions runs. Do not say a command or check passed until its output or hosted result proves it.

## Pull request summary

Every pull request must include these fields and direct links where requested:

Simulation case:
Rules added, changed, and removed (IDs or write none):
Old behavior:
New behavior:
Tests added: none | paths and links
Tests removed: none | paths and links
Relevant tests and runs: direct links
Reviewer role: simulated by an independent agent | not required

Use none when no test was added or removed. Keep each summary tied to its exact head. The summary helps readers find evidence; it does not replace the diff, test runs, evaluator result, or merge status.

## Review routing and merge policy

Apply this order:

1. Block any removal or rename of a required test. A simulated verdict cannot waive this block.
2. Require an accepted simulated reviewer verdict for a judgment change. The verdict must match the current pull request head. Unknown or stale changes stay blocked.
3. Allow the exact trusted routine example without a reviewer verdict only after its exact patch matches the protected rule and every required check passes.

Use a trusted evaluator that reads its rules from the protected target branch. A pull request cannot change the rules, required-test hashes, or check configuration that judges that pull request. Fail closed when data is missing, stale, malformed, unknown, or conflicting. Do not decide by file count, model label, pull request label, or a claim in the pull request.

For a judgment example, an independent reviewer agent must inspect the actual diff and test evidence. Clearly label every reviewer-role input as simulated. Exercise the evaluator with a negative decision first and a positive decision second for the same pull request head, then record both policy statuses. These are synthetic fixture inputs, not human decisions. Do not create or claim a native GitHub review or human approval. If the independent review finds a real issue and the code changes, review the new head and bind the result to that head.

The exact routine patch is a planned example, not proof of semantic equivalence. Store its full patch digest and changed-path set in trusted policy before opening its pull request. Any extra hunk, file, changed test, unexpected base, or policy input routes to review.

## Evidence and privacy

- Record the exact request, rule IDs, Gherkin path, artifact hashes, and pre-code checks before full feature implementation.
- For each example, retain the actual pull request URL, commit permalink, exact head SHA, test and evaluator run links, decision and reason, and actual merged or blocked state.
- Capture screenshots only from real public pull request, check, and evaluator pages. Do not create or edit screenshots to imply a result.
- Keep the red and green test results tied to their own revisions. Keep local and hosted results distinct.
- Report only facts proved by the linked evidence. Do not claim that a demo rule works before its real checks and GitHub state prove it.
- Keep private planning material, credentials, and local paths out of this public repository. Do not publish a post or contact a person as part of this demonstration.

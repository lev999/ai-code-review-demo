# AI code review demo

This repository demonstrates review decisions for a small task board. The feature request, product rules, and reviewer-role inputs are simulated examples written for this project. An independent agent can simulate the reviewer role. A simulated verdict is not a GitHub review or human approval.

## Implemented feature

The board starts with two tasks in **To do**. The initial one-task rule lets a user move exactly one selected task through the existing one-task API. The agent-authored simulated product decision in [the two-task behavior spec](specs/move-two-tasks.feature) changes the selection rule to allow one or two tasks. A two-task move uses a separate batch API and saves both rows in one SQLite transaction. The one-task API contract and reload behavior stay in place.

The checks cover button state, the one-task API, the two-task API, browser persistence, and SQLite rows. They also cover unknown task IDs, tasks outside **To do**, and a mixed two-task batch that must leave both rows unchanged.

## Run locally

Use Node.js, npm, Python 3, and Google Chrome. The project needs no Python packages.

```sh
make setup
make verify
```

`make setup` installs the locked Playwright dependency with `npm ci`. `make verify` runs the bootstrap smoke tests, component tests, API tests, and real-browser checks. The browser check uses the installed Google Chrome through Playwright. You can also run `make smoke`, `make component`, `make api`, or `make browser` on its own.

The service seeds an empty database with **Write one small test** and **Check the board state**. It uses SQLite and reads the database path from `DEMO_DB_PATH` when that variable is set. Tests use temporary databases.

## Hosted feature record

[Pull request #4](https://github.com/lev999/ai-code-review-demo/pull/4) is merged at [merge commit `1bb96ff`](https://github.com/lev999/ai-code-review-demo/commit/1bb96ff0dc41e6cfecdcd3521653ebbdc23762c3). Its final reviewed head was `d5ae35f0ae14c41d77a28b36e3a3f6f1b2ca8a95`.

- The test-only red run failed at `f0b53c98878cfb6dbc114592e71d44a74aaf2cc5`, before task movement was implemented: [red run](https://github.com/lev999/ai-code-review-demo/actions/runs/45890153327).
- The first implementation run passed at `027c33f990b4a7152f882eaf9e16d0dc87e26993`: [green run](https://github.com/lev999/ai-code-review-demo/actions/runs/45890636818).
- The final reviewed head passed the hosted `demo-tests` job: [job for `d5ae35f`](https://github.com/lev999/ai-code-review-demo/actions/runs/45891136067/job/140153813910). The accepted simulated verdict is in [the review comment](https://github.com/lev999/ai-code-review-demo/pull/4#issuecomment-7202739546), and the trusted policy run is [here](https://github.com/lev999/ai-code-review-demo/actions/runs/45891393581).

## H7 trusted policy scope

This is a controlled demonstration, not a general AI risk classifier. The H6 bootstrap gate protected `tests/test_move.py` and `tests/test_preserve.py`; it did not protect the feature tests. The H7 policy contract adds trusted rules for the full feature checks.

The H7 contract uses the gate and manifest from the protected target branch. The manifest binds each required test ID and path to a SHA-256 hash. The gate checks the pull request base and head against those trusted files. Missing or renamed required tests are blocked before routine or reviewer classification, even if a simulated verdict accepts the change.

The routine example is allowed only when its full patch digest and changed-path set match the trusted entry and the actual CI checks pass on the same head. Other changes need an independent agent's simulated review. Automation records the verdict in a bot-authored comment tied to the exact head SHA. The gate validates the bot source, case, verdict, evidence, and current head. A missing, stale, malformed, conflicting, or `changes_requested` verdict stays blocked. The comment is not a GitHub review or human approval.

Policy fixtures check the allowlisted routine, an unknown change with a current accepted verdict, and required-test removal even with an accepted verdict. These fixtures check controlled policy decisions. They do not prove platform outcomes for the planned H8 routine, H9 judgment, or H10 test-removal pull requests.

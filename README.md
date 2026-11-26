# AI code review demo

This repository demonstrates review decisions for a small task board. The feature request, product rules, and reviewer-role inputs are simulated examples written for this project. An independent agent can simulate the reviewer role. A simulated verdict is not a GitHub review or human approval.

## Implemented feature

The board starts with two tasks in **To do**. When exactly one task is selected, the user can move it to **Done**. The app saves the move in SQLite. After reload, both lists show the saved state, and the other task stays in **To do**.

The checks cover button state, API behavior, browser persistence, and SQLite rows. The API also checks unknown task IDs and tasks that are not in **To do**.

## Run locally

Use Node.js, npm, Python 3, and Google Chrome. The project needs no Python packages.

```sh
make setup
make verify
```

`make setup` installs the locked Playwright dependency with `npm ci`. `make verify` runs the bootstrap smoke tests, component tests, API tests, and real-browser checks. The browser check uses the installed Google Chrome through Playwright. You can also run `make smoke`, `make component`, `make api`, or `make browser` on its own.

The service seeds an empty database with **Write one small test** and **Check the board state**. It uses SQLite and reads the database path from `DEMO_DB_PATH` when that variable is set. Tests use temporary databases.

## Hosted feature evidence

[Pull request #4](https://github.com/lev999/ai-code-review-demo/pull/4) shows the test-first feature change. The red run failed on test-only commit `f0b53c98878cfb6dbc114592e71d44a74aaf2cc5`, when moving a task was not implemented. The green run passed on implementation commit `027c33f990b4a7152f882eaf9e16d0dc87e26993`.

- [Red hosted run](https://github.com/lev999/ai-code-review-demo/actions/runs/45890153327)
- [Green hosted run](https://github.com/lev999/ai-code-review-demo/actions/runs/45890636818)

## Review policy scope

This is a controlled demonstration, not a general AI risk classifier. The current trusted gate recognizes one exact routine refactor. Unclassified changes need a simulated reviewer decision. The gate blocks removal or rename of its two configured smoke tests, `tests/test_move.py` and `tests/test_preserve.py`.

The feature tests in `web/tests/task_state.test.js`, `api/tests/test_tasks_api.py`, and `web/tests/e2e/test_board.mjs` are present and run by `make verify`, but the current trusted test list does not protect them yet. The planned H7 policy update will add them. The current workflow checks that a dispatched decision names the current pull request head. It does not validate the source or evidence in a verdict comment.

The gate does not decide that a change is safe from its size, filenames, labels, or model output. Simulated review decisions are examples only; they do not count as human approval.

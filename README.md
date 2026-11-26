# AI code review demo

This repository contains a controlled demonstration of review decisions for a small task board. It uses original task data. Feature requests, product rules, and reviewer-role decisions in the examples are simulated.

The first scenario is a user selecting one task and moving it from **To do** to **Done**. The current baseline reads the two seeded tasks from SQLite. It does not yet move a task. The feature tests describe the expected behavior and are expected to fail until the feature is implemented.

## Run locally

Use Node.js, npm, Python 3, and Google Chrome. No Python packages are required.

```sh
make setup
make verify
```

`make verify` runs the existing policy smoke tests and the component, API, and browser checks as separate commands. The browser check uses the installed Google Chrome through Playwright. You can also run `make smoke`, `make component`, `make api`, or `make browser` on its own. `make setup` uses the checked-in npm lock file.

The local service seeds a fresh database with **Write one small test** and **Check the board state**. It uses SQLite and reads the database path from `DEMO_DB_PATH` when that variable is set.

## Scope

These are controlled demonstrations, not a general AI risk classifier. A routine decision applies only to an exact pre-approved patch. Unknown changes need a simulated reviewer decision. Removal of a required test is blocked. Tests, code, and workflow runs provide evidence for each result; a simulated reviewer decision is not a human approval.

The repository does not claim that a change is safe because of its size, file names, labels, or model output.

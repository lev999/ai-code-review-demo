# SIMULATED FEATURE REQUEST: see the exact, immutable brief in synthetic-feature-request.md.
# The source brief is labeled SYNTHETIC FEATURE REQUEST; no person supplied or approved it.
# SIMULATED PRODUCT RULES: RULE-BOARD-001, RULE-BOARD-002, RULE-SELECT-001,
# RULE-SELECT-002, RULE-MOVE-001, RULE-SAVE-001, RULE-API-001..003, RULE-DATA-001.
# These scenarios define behavior before implementation. Planned executable checks:
# - Component: web/tests/task_state.test.js
# - API and SQLite rows: api/tests/test_tasks_api.py
# - Real browser, reload, and SQLite state: web/tests/e2e/test_board.mjs

Feature: Move one selected task from To do to Done
  The initial feature moves exactly one selected task and keeps the other task in To do.

  Background:
    Given a fresh demo database
    And the database contains these tasks:
      | id      | title                 | list |
      | task-1  | Write one small test  | todo |
      | task-2  | Check the board state | todo |

  @RULE-SELECT-001 @RULE-SELECT-002
  # Executable check: web/tests/task_state.test.js, no-selection button state.
  Scenario: Keep Move selected disabled when no task is selected
    Given the board is displayed
    When no task is selected
    Then the Move selected button is disabled

  @RULE-SELECT-002 @RULE-MOVE-001
  # Executable checks: api/tests/test_tasks_api.py, one-row move; web/tests/e2e/test_board.mjs, selected task and unchanged second task.
  Scenario: Move only the selected task
    Given the board is displayed
    When I select task "task-1"
    And I activate the Move selected button
    Then task "task-1" is in Done
    And task "task-2" is in To do
    And the database contains only task "task-1" in Done

  @RULE-SAVE-001 @RULE-MOVE-001 @RULE-DATA-001
  # Executable check: web/tests/e2e/test_board.mjs, real reload, both lists, and SQLite rows.
  Scenario: Preserve both list contents after reload
    Given task "task-1" has been moved to Done
    When I reload the board
    Then task "task-1" is in Done
    And task "task-2" is in To do
    And the SQLite rows show task "task-1" in Done and task "task-2" in To do

  @RULE-API-001 @RULE-API-002 @RULE-API-003
  # Executable check: api/tests/test_tasks_api.py, successful move response and row comparison.
  Scenario: Return the moved task from the API
    When I move task "task-1" to Done through the API
    Then the API returns status 200
    And the API response is {"id":"task-1","list":"done"}
    And the other task remains in To do

  @RULE-API-003
  # Executable check: api/tests/test_tasks_api.py, unknown ID returns 404 without changing rows.
  Scenario: Reject an unknown task ID
    When I move unknown task "missing-task" to Done through the API
    Then the API returns status 404
    And neither seeded task changes lists

  @RULE-API-003
  # Executable check: api/tests/test_tasks_api.py, non-To-do task returns 409 without changing rows.
  Scenario: Reject a task that is not in To do
    Given task "task-1" is already in Done
    When I move task "task-1" to Done through the API
    Then the API returns status 409
    And neither seeded task changes lists

# SIMULATED PRODUCT DECISION: an agent-authored simulation, not a user-provided requirement.
# Changed rule: RULE-SELECT-002.
# Old behavior: Move selected accepts exactly one task in To do; two selected tasks are disabled.
# New behavior: Move selected accepts one or two distinct tasks in To do; two move together in one transaction.
# Preserved behavior: one selected task still uses POST /api/tasks/{task_id}/move-to-done and keeps its response contract.
# Added rules: RULE-MOVE-002 (the two-task move is atomic), RULE-API-004 (POST /api/tasks/move-selected-to-done
# accepts {"task_ids":[id1,id2]} and returns {"ids":[id1,id2],"list":"done"}; unknown IDs return 404,
# a task outside To do returns 409, and a malformed or duplicate-ID request returns 400).
# Executable checks: web/tests/task_state.test.js; api/tests/test_batch_tasks_api.py;
# web/tests/e2e/test_batch_moves.mjs. The existing one-task checks remain in their original files.

Feature: Move two selected tasks together
  This simulated product decision extends the initial one-task behavior without changing its API contract.

  Background:
    Given a fresh demo database
    And the database contains task "task-1" named "Write one small test" in To do
    And the database contains task "task-2" named "Check the board state" in To do

  @RULE-SELECT-002 @RULE-MOVE-002 @RULE-API-004
  # Executable checks: component enables two selections; api/tests/test_batch_tasks_api.py and
  # web/tests/e2e/test_batch_moves.mjs move both rows.
  Scenario: Move two selected tasks together
    Given the board is displayed
    When I select tasks "task-1" and "task-2"
    And I activate the Move selected button
    Then both tasks are in Done
    And no task remains in To do
    And both SQLite rows show Done after reload

  @RULE-MOVE-002 @RULE-API-004
  # Executable checks: api/tests/test_batch_tasks_api.py and web/tests/e2e/test_batch_moves.mjs
  # reject a mixed batch and compare both persisted rows.
  Scenario: Reject an invalid mixed batch without a partial move
    Given task "task-2" is in Done and task "task-1" is in To do
    When I request a batch move for "task-1" and "task-2"
    Then the API returns status 409
    And task "task-1" remains in To do
    And task "task-2" remains in Done
    And both SQLite rows are unchanged after reload

  @RULE-API-002 @RULE-API-004
  # Executable check: api/tests/test_tasks_api.py verifies the unchanged one-task request and response.
  Scenario: Keep the one-task API contract
    When I move task "task-1" through POST /api/tasks/task-1/move-to-done
    Then the API returns status 200
    And the API response is {"id":"task-1","list":"done"}

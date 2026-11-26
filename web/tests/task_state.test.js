import assert from "node:assert/strict";
import test from "node:test";

import { canMoveSelected } from "../src/task_state.js";

test("Move selected is disabled when no task is selected", () => {
  assert.equal(canMoveSelected([], ["task-1", "task-2"]), false);
});

test("Move selected is enabled for exactly one selected To do task", () => {
  assert.equal(canMoveSelected(["task-1"], ["task-1", "task-2"]), true);
});

test("Simulated RULE-SELECT-002 change enables exactly two selected To do tasks", () => {
  // The initial rule disabled this two-task selection; the simulated decision enables it.
  assert.equal(canMoveSelected(["task-1", "task-2"], ["task-1", "task-2"]), true);
});

test("Simulated RULE-SELECT-002 keeps three selected tasks disabled", () => {
  assert.equal(canMoveSelected(["task-1", "task-2", "task-3"], ["task-1", "task-2", "task-3"]), false);
});

test("Move selected is disabled for a task outside To do", () => {
  assert.equal(canMoveSelected(["task-done"], ["task-1", "task-2"]), false);
});

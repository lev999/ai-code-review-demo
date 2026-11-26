import assert from "node:assert/strict";
import test from "node:test";

import { canMoveSelected } from "../src/task_state.js";

test("Move selected is disabled when no task is selected", () => {
  assert.equal(canMoveSelected([], ["task-1", "task-2"]), false);
});

test("Move selected is enabled for exactly one selected To do task", () => {
  assert.equal(canMoveSelected(["task-1"], ["task-1", "task-2"]), true);
});

test("Move selected is disabled when more than one task is selected", () => {
  assert.equal(canMoveSelected(["task-1", "task-2"], ["task-1", "task-2"]), false);
});

test("Move selected is disabled for a task outside To do", () => {
  assert.equal(canMoveSelected(["task-done"], ["task-1", "task-2"]), false);
});

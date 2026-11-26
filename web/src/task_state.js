// RULE-SELECT-001 and the simulated RULE-SELECT-002 change: one or two distinct To do tasks can be moved.
export function canMoveSelected(selectedIds, todoIds) {
  return (
    (selectedIds.length === 1 || selectedIds.length === 2) &&
    new Set(selectedIds).size === selectedIds.length &&
    selectedIds.every((taskId) => todoIds.includes(taskId))
  );
}

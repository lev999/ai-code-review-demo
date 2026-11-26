// RULE-SELECT-001 and RULE-SELECT-002: only one task in To do can be moved.
export function canMoveSelected(selectedIds, todoIds) {
  return selectedIds.length === 1 && todoIds.includes(selectedIds[0]);
}

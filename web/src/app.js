import { canMoveSelected } from "/src/task_state.js";

const todoList = document.querySelector("#todo-list");
const doneList = document.querySelector("#done-list");
const moveButton = document.querySelector("#move-selected");
const status = document.querySelector("#board-status");
const selectedIds = new Set();
let todoIds = [];

function updateMoveButton() {
  moveButton.disabled = !canMoveSelected([...selectedIds], todoIds);
}

function renderList(element, tasks, selectable) {
  element.replaceChildren();
  for (const task of tasks) {
    const item = document.createElement("li");
    if (selectable) {
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = task.id;
      checkbox.setAttribute("aria-label", task.title);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) selectedIds.add(task.id);
        else selectedIds.delete(task.id);
        updateMoveButton();
      });
      label.append(checkbox, document.createTextNode(task.title));
      item.append(label);
    } else {
      item.textContent = task.title;
    }
    element.append(item);
  }
}

async function loadBoard() {
  const response = await fetch("/api/tasks");
  if (!response.ok) throw new Error(`Task request failed: ${response.status}`);
  const { lists } = await response.json();
  selectedIds.clear();
  todoIds = lists.todo.map((task) => task.id);
  renderList(todoList, lists.todo, true);
  renderList(doneList, lists.done, false);
  updateMoveButton();
}

moveButton.addEventListener("click", async () => {
  if (!canMoveSelected([...selectedIds], todoIds)) return;

  const taskIds = [...selectedIds];
  const isBatchMove = taskIds.length === 2;
  moveButton.disabled = true;
  status.textContent = isBatchMove ? "Moving tasks…" : "Moving task…";
  try {
    const endpoint = isBatchMove
      ? "/api/tasks/move-selected-to-done"
      : `/api/tasks/${encodeURIComponent(taskIds[0])}/move-to-done`;
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(isBatchMove ? { task_ids: taskIds } : {}),
    });
    if (!response.ok) {
      throw new Error(`Move request failed: ${response.status}`);
    }
    selectedIds.clear();
    await loadBoard();
    status.textContent = isBatchMove ? "Tasks moved to Done." : "Task moved to Done.";
  } catch (error) {
    status.textContent = "The task could not be moved.";
    updateMoveButton();
    console.error(error);
  }
});

loadBoard().catch((error) => {
  status.textContent = "The task board could not load.";
  console.error(error);
});

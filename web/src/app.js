import { canMoveSelected } from "/src/task_state.js";

const todoList = document.querySelector("#todo-list");
const doneList = document.querySelector("#done-list");
const moveButton = document.querySelector("#move-selected");
const status = document.querySelector("#board-status");
const selectedIds = new Set();
let todoIds = [];

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
        moveButton.disabled = !canMoveSelected([...selectedIds], todoIds);
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
  todoIds = lists.todo.map((task) => task.id);
  renderList(todoList, lists.todo, true);
  renderList(doneList, lists.done, false);
}

loadBoard().catch((error) => {
  status.textContent = "The task board could not load.";
  console.error(error);
});

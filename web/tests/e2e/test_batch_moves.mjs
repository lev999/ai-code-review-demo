import assert from "node:assert/strict";
import { execFile, spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import { chromium } from "playwright";

const execFileAsync = promisify(execFile);
const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

test("two selected tasks move together, persist after reload, and change both SQLite rows", async () => {
  const temporaryDirectory = await mkdtemp(path.join(tmpdir(), "task-board-browser-two-"));
  const dbPath = path.join(temporaryDirectory, "tasks.sqlite3");
  const service = await startService(dbPath);
  let browser;
  try {
    browser = await chromium.launch({ channel: process.env.CHROME_CHANNEL || "chrome", headless: true });
    const page = await browser.newPage();
    await page.goto(service.url, { waitUntil: "networkidle" });

    const moveButton = page.getByRole("button", { name: "Move selected" });
    await page.getByRole("checkbox", { name: "Write one small test" }).check();
    await page.getByRole("checkbox", { name: "Check the board state" }).check();
    assert.equal(await moveButton.isEnabled(), true, "button enables for two To do tasks");
    await moveButton.click();
    await assertLists(page, [], ["Write one small test", "Check the board state"]);

    await page.reload({ waitUntil: "networkidle" });
    await assertLists(page, [], ["Write one small test", "Check the board state"]);
    const databaseOutput = await execFileAsync("python3", ["scripts/read_db.py", dbPath], { cwd: repositoryRoot });
    assert.deepEqual(JSON.parse(databaseOutput.stdout), { "task-1": "done", "task-2": "done" });
  } finally {
    if (browser) await browser.close();
    service.child.kill();
    if (service.child.exitCode === null) await once(service.child, "exit");
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
});

test("invalid mixed batch stays unchanged in the browser and SQLite", async () => {
  const temporaryDirectory = await mkdtemp(path.join(tmpdir(), "task-board-browser-mixed-"));
  const dbPath = path.join(temporaryDirectory, "tasks.sqlite3");
  const service = await startService(dbPath);
  let browser;
  try {
    browser = await chromium.launch({ channel: process.env.CHROME_CHANNEL || "chrome", headless: true });
    const page = await browser.newPage();
    await page.goto(service.url, { waitUntil: "networkidle" });

    // Use the unchanged one-task API to prepare one To do row and one Done row.
    const setupStatus = await page.evaluate(async () => {
      const response = await fetch("/api/tasks/task-2/move-to-done", { method: "POST", body: "{}" });
      return response.status;
    });
    assert.equal(setupStatus, 200);
    await page.reload({ waitUntil: "networkidle" });
    await assertLists(page, ["Write one small test"], ["Check the board state"]);

    const batchResult = await page.evaluate(async () => {
      const response = await fetch("/api/tasks/move-selected-to-done", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_ids: ["task-1", "task-2"] }),
      });
      return { status: response.status, body: await response.json() };
    });
    assert.equal(batchResult.status, 409, "mixed To do/Done batch is rejected");

    await page.reload({ waitUntil: "networkidle" });
    await assertLists(page, ["Write one small test"], ["Check the board state"]);
    const databaseOutput = await execFileAsync("python3", ["scripts/read_db.py", dbPath], { cwd: repositoryRoot });
    assert.deepEqual(JSON.parse(databaseOutput.stdout), { "task-1": "todo", "task-2": "done" });
  } finally {
    if (browser) await browser.close();
    service.child.kill();
    if (service.child.exitCode === null) await once(service.child, "exit");
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
});

async function assertLists(page, todoTitles, doneTitles) {
  const todoTasks = page.getByRole("list", { name: "To do tasks" });
  const doneTasks = page.getByRole("list", { name: "Done tasks" });
  for (const title of todoTitles) await todoTasks.getByText(title, { exact: true }).waitFor();
  for (const title of doneTitles) await doneTasks.getByText(title, { exact: true }).waitFor();
  assert.deepEqual(await todoTasks.locator("li").allTextContents(), todoTitles);
  assert.deepEqual(await doneTasks.locator("li").allTextContents(), doneTitles);
}

async function startService(dbPath) {
  const child = spawn(
    "python3",
    ["-m", "api.app", dbPath],
    { cwd: repositoryRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  const lines = createInterface({ input: child.stdout });
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Task API did not start in time")), 10000);
    lines.once("line", (line) => {
      clearTimeout(timer);
      resolve(Number(line));
    });
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Task API exited before startup (code ${code})`));
    });
  });
  assert.ok(Number.isInteger(port) && port > 0, "Task API reports a local port");
  return { child, url: `http://127.0.0.1:${port}` };
}

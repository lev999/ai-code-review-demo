import assert from "node:assert/strict";
import { execFile, spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import { chromium } from "playwright";

const execFileAsync = promisify(execFile);
const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

test("one selected task moves, persists after reload, and changes one SQLite row", async () => {
  const temporaryDirectory = await mkdtemp(path.join(tmpdir(), "task-board-browser-"));
  const dbPath = path.join(temporaryDirectory, "tasks.sqlite3");
  const service = await startService(dbPath);
  let browser;
  try {
    browser = await chromium.launch({ channel: process.env.CHROME_CHANNEL || "chrome", headless: true });
    const page = await browser.newPage();
    await page.goto(service.url, { waitUntil: "networkidle" });

    const moveButton = page.getByRole("button", { name: "Move selected" });
    assert.equal(await moveButton.isDisabled(), true, "button starts disabled");
    await page.getByRole("checkbox", { name: "Write one small test" }).check();
    assert.equal(await moveButton.isEnabled(), true, "button enables after one To do task is selected");

    await moveButton.click();
    const todoTasks = page.getByRole("list", { name: "To do tasks" });
    const doneTasks = page.getByRole("list", { name: "Done tasks" });
    await assertTaskLists(todoTasks, doneTasks);

    await page.reload({ waitUntil: "networkidle" });
    await assertTaskLists(
      page.getByRole("list", { name: "To do tasks" }),
      page.getByRole("list", { name: "Done tasks" }),
    );

    const databaseOutput = await execFileAsync("python3", ["scripts/read_db.py", dbPath], { cwd: repositoryRoot });
    assert.deepEqual(JSON.parse(databaseOutput.stdout), {
      "task-1": "done",
      "task-2": "todo",
    });

    await mkdir(path.join(repositoryRoot, "artifacts"), { recursive: true });
    await page.screenshot({ path: path.join(repositoryRoot, "artifacts", "task-board.png"), fullPage: true });
  } finally {
    if (browser) await browser.close();
    service.child.kill();
    if (service.child.exitCode === null) await once(service.child, "exit");
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
});

async function assertTaskLists(todoTasks, doneTasks) {
  await todoTasks.getByText("Check the board state", { exact: true }).waitFor();
  await doneTasks.getByText("Write one small test", { exact: true }).waitFor();
  assert.equal(await todoTasks.getByText("Write one small test", { exact: true }).count(), 0);
  assert.equal(await doneTasks.getByText("Check the board state", { exact: true }).count(), 0);
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

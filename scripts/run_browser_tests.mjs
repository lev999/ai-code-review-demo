import { readdirSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const testDirectory = path.resolve(scriptDirectory, "../web/tests/e2e");
const requiredTest = "test_board.mjs";
const testFiles = readdirSync(testDirectory)
  .filter((file) => /^test_.*\.mjs$/.test(file))
  .sort();
let missingRequiredTest = false;

if (!testFiles.includes(requiredTest)) {
  console.error(`Required persistence test is missing: web/tests/e2e/${requiredTest}`);
  missingRequiredTest = true;
}

if (testFiles.length === 0) {
  console.error("No browser test files were found.");
  process.exitCode = 1;
} else {
  const paths = testFiles.map((file) => path.join(testDirectory, file));
  const result = spawnSync(process.execPath, ["--test", ...paths], {
    env: process.env,
    stdio: "inherit",
  });
  if (result.error) {
    console.error("Could not start the browser test runner.");
    process.exitCode = 1;
  } else if (result.status !== 0) {
    process.exitCode = result.status ?? 1;
  }
}

if (missingRequiredTest) process.exitCode = 1;

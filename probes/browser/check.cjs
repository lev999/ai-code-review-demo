const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const { mkdtemp, rm } = require("node:fs/promises");
const { tmpdir } = require("node:os");
const path = require("node:path");

async function main() {
  const dir = await mkdtemp(path.join(tmpdir(), "board-probe-"));
  const service = spawn("python3", [path.join(__dirname, "server.py"), path.join(dir, "probe.db")]);
  let browser;
  try {
    const [output] = await once(service.stdout, "data");
    const port = Number(output.toString().trim());
    assert(Number.isInteger(port) && port > 0);
    browser = await chromium.launch(process.env.CHROME_CHANNEL ? {channel: process.env.CHROME_CHANNEL} : {});
    const page = await browser.newPage();
    await page.goto("http://127.0.0.1:" + port);
    await page.reload();
    assert.deepEqual(JSON.parse(await page.locator("body").innerText()), {value: 1});
    await page.screenshot({path: "browser-preflight.png"});
    console.log("Browser read SQLite through HTTP after reload. Screenshot saved.");
  } finally {
    if (browser) await browser.close();
    service.kill();
    await rm(dir, { recursive: true, force: true });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

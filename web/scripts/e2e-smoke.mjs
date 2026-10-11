// End-to-end smoke check against a running dev server and API: log in, run a request on
// /app/ask, wait for the result, and save screenshots of each screen.
//   node scripts/e2e-smoke.mjs [baseUrl]
import { mkdirSync } from "node:fs";

import { chromium } from "playwright";

const base = process.argv[2] ?? "http://127.0.0.1:5173";
const out = new URL("../test-results/screens/", import.meta.url).pathname;
mkdirSync(out, { recursive: true });

// Uses the installed Google Chrome, so no browser download is needed.
const browser = await chromium.launch({ channel: "chrome" });
for (const [name, viewport] of [
  ["desktop", { width: 1440, height: 900 }],
  ["mobile", { width: 390, height: 844 }],
]) {
  const page = await browser.newPage({ viewport });
  page.on("pageerror", (e) => console.log(`[${name}] page error:`, e.message));

  await page.goto(`${base}/?capture`);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}landing-${name}.png` });
  await page.screenshot({ path: `${out}landing-${name}-full.png`, fullPage: true });

  await page.goto(`${base}/login`);
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}login-${name}.png` });
  await page.fill("#email", "demo@nument.dev");
  await page.fill("#password", "nument-demo-2026");
  await page.click("button[type=submit]");
  await page.waitForURL("**/app/ask**");
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${out}ask-empty-${name}.png` });

  if (name === "desktop") {
    await page.fill("textarea", "Allocate this week's orders.");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${out}ask-running-${name}.png` });
    await page.waitForSelector("text=Plan checks", { timeout: 120_000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${out}ask-result-${name}.png` });
    await page.screenshot({ path: `${out}ask-result-${name}-full.png`, fullPage: true });
  }
  await page.close();
}
await browser.close();
console.log(`screenshots in ${out}`);

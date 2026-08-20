import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { chromium } = require(path.resolve(here, "../frontend/node_modules/playwright-core"));
const output = path.resolve(process.env.RESUME_DETECTIVE_SCREENSHOT_DIR || path.join(here, "../.tmp-build/public-screenshots"));
const port = process.env.RESUME_DETECTIVE_QA_PORT || "18765";
fs.mkdirSync(output, { recursive: true });

const candidates = [
  process.env.PLAYWRIGHT_CHROMIUM_PATH,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No Chromium-compatible browser found");

const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
const errors = [];
page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });

async function capture(route, heading, filename) {
  await page.goto(`http://127.0.0.1:${port}/#/${route}`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: heading }).waitFor();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, filename), fullPage: false });
}

// Regression: ordinary navigation must never reuse the top-bar "new application" signal.
await page.goto(`http://127.0.0.1:${port}/#/overview`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "投递管理", exact: true }).click();
if (await page.locator('[role="dialog"]').count()) throw new Error("Applications navigation opened the new-application dialog");
await page.getByRole("button", { name: "新建投递" }).click();
await page.getByRole("dialog", { name: "新建投递" }).waitFor();
await page.getByRole("button", { name: "关闭" }).click();
await page.getByRole("button", { name: "总览", exact: true }).click();
await page.getByRole("button", { name: "投递管理", exact: true }).click();
if (await page.locator('[role="dialog"]').count()) throw new Error("Consumed new-application signal reopened after navigation");

await capture("overview", "秋招工作台", "v4-overview.png");
await capture("applications", "投递管理", "v4-applications.png");
await capture("targets", "意向清单", "v4-targets.png");
await capture("tasks", "行动清单", "v4-tasks.png");
await capture("interviews", "面试复盘", "v4-interviews.png");
await capture("offers", "Offer 对比", "v4-offers.png");
await capture("resumes", "简历汇总", "v4-resumes.png");
await capture("profile", "个人资料库", "v4-profile.png");
await capture("ai", "岗位准备助手", "v4-ai.png");
await capture("settings", "设置", "v4-settings.png");

if (errors.length) throw new Error(`browser console errors: ${errors.join(" | ")}`);
await browser.close();
console.log(`Public screenshot QA passed: ${output}`);

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { chromium } = require(path.resolve(here, "../frontend/node_modules/playwright-core"));
const output = path.resolve(here, "../.qa-output");
fs.mkdirSync(output, { recursive: true });
const sampleResume = path.join(output, "sample-resume.pdf");
fs.writeFileSync(sampleResume, "%PDF-1.4\n% ResumeDetective QA\n%%EOF");
const port = process.env.RESUME_DETECTIVE_QA_PORT || "18765";

const browserCandidates = [
  process.env.PLAYWRIGHT_CHROMIUM_PATH,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No Chromium-compatible browser found for QA");
const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
const errors = [];
page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });

await page.goto(`http://127.0.0.1:${port}`, { waitUntil: "networkidle" });
await page.getByRole("heading", { name: "秋招工作台" }).waitFor();
await page.screenshot({ path: path.join(output, "01-overview-empty.png"), fullPage: false });

await page.getByRole("button", { name: "新建投递" }).first().click();
await page.getByLabel("公司名称").fill("浏览器验证公司");
await page.getByLabel("岗位名称").fill("Go 后端开发");
await page.getByLabel("城市").fill("上海");
await page.getByLabel("岗位类型").fill("研发");
await page.getByLabel("自定义标签").fill("Go, 校招");
await page.getByLabel("绑定简历").setInputFiles(sampleResume);
await page.getByLabel("JD 原文").fill("负责本地优先的求职工作台开发，要求掌握 Go、SQLite 与 Web 服务。" );
await page.getByRole("button", { name: "保存投递" }).click();
await page.getByText("浏览器验证公司").first().waitFor();

await page.getByPlaceholder("搜索公司、岗位或标签").fill("Go");
await page.getByText("Go 后端开发").first().waitFor();
await page.getByRole("button", { name: "管理" }).click();
await page.getByLabel("当前环节").selectOption("测评");
await page.getByLabel("环节状态").selectOption("已完成，等待结果");
await page.getByLabel("下一步行动").fill("等待测评结果");
await page.getByRole("button", { name: "保存修改" }).click();
await page.getByText("已投递 → 测评").waitFor();
await page.evaluate(() => window.scrollTo(0, 0));
await page.screenshot({ path: path.join(output, "02-applications-expanded.png"), fullPage: false });

await page.getByRole("button", { name: "意向清单" }).click();
await page.getByRole("button", { name: "添加意向" }).click();
await page.getByLabel("公司名称").fill("意向公司");
await page.getByLabel("岗位名称").fill("供应链管培生");
await page.getByLabel("状态").selectOption("待投递");
await page.getByLabel("城市").fill("苏州");
await page.getByLabel("JD 原文").fill("负责供应链计划与跨部门协同。" );
await page.getByRole("button", { name: "保存", exact: true }).click();
await page.getByText("供应链管培生").waitFor();
await page.screenshot({ path: path.join(output, "03-targets.png"), fullPage: false });

await page.getByRole("button", { name: "行动清单" }).click();
await page.getByPlaceholder("例如：复习 MySQL 索引").fill("浏览器验证待办");
await page.getByRole("button", { name: "添加" }).click();
await page.getByText("浏览器验证待办").waitFor();

await page.getByRole("button", { name: "面试复盘" }).click();
await page.getByRole("button", { name: "记录面试" }).click();
await page.getByLabel("对应岗位").selectOption({ label: "浏览器验证公司 · Go 后端开发" });
await page.getByLabel("整体总结").fill("基础功能浏览器验证");
await page.getByLabel("主要问题").fill("Go 并发模型");
await page.getByLabel("薄弱点").fill("调度细节");
await page.getByLabel("后续行动").fill("复习调度器");
await page.getByRole("button", { name: "保存复盘" }).click();
await page.getByText("基础功能浏览器验证").waitFor();

await page.getByRole("button", { name: "简历汇总" }).click();
await page.getByRole("link", { name: /查看简历/ }).waitFor();
await page.screenshot({ path: path.join(output, "04-resumes.png"), fullPage: false });

await page.getByRole("button", { name: "设置" }).click();
await page.getByRole("heading", { name: "AI Provider" }).waitFor();
await page.screenshot({ path: path.join(output, "05-settings.png"), fullPage: false });

if (errors.length) throw new Error(`browser console errors: ${errors.join(" | ")}`);
await browser.close();
console.log(`QA passed; screenshots: ${output}`);

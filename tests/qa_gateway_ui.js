const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');

(async () => {
  const browserCandidates = [
    process.env.PLAYWRIGHT_CHROME_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  ].filter(Boolean);
  const executablePath = browserCandidates.find(candidate => fs.existsSync(candidate));
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });
  const keepScreenshots = process.env.KEEP_QA_SCREENSHOTS === '1';
  const outputDir = process.env.QA_SCREENSHOT_DIR || fs.mkdtempSync(path.join(os.tmpdir(), 'resume-detective-qa-'));
  fs.mkdirSync(outputDir, { recursive: true });
  const consoleErrors = [];
  for (const viewport of [
    { name: 'desktop', width: 1440, height: 1000 },
    { name: 'narrow', width: 430, height: 900 },
  ]) {
    const page = await browser.newPage({ viewport: viewport });
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(`${viewport.name}: ${msg.text()}`); });
    page.on('pageerror', error => consoleErrors.push(`${viewport.name}: ${error.message}`));
    for (const route of ['/', '/board', '/applications', '/interviews', '/resumes']) {
      await page.goto(`http://127.0.0.1:18765${route}`, { waitUntil: 'networkidle' });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
      if (overflow) throw new Error(`${viewport.name} ${route}: page-level horizontal overflow`);
      const name = route === '/' ? 'overview' : route.slice(1);
      await page.screenshot({ path: `${outputDir}/${viewport.name}-${name}.png`, fullPage: true });
    }
    await page.goto('http://127.0.0.1:18765/board', { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: '表格' }).click();
    if (!(await page.locator('#boardView').getAttribute('class')).includes('hidden')) throw new Error('board view did not hide');
    if ((await page.locator('#tableView').getAttribute('class')).includes('hidden')) throw new Error('table view did not show');
    const archivedRows = page.locator('#boardTableRows tr[data-archived="1"]');
    if (await archivedRows.count()) {
      if (!(await archivedRows.first().getAttribute('class')).includes('hidden')) throw new Error('terminated row should be hidden by default');
      await page.locator('#toggleTerminated').click();
      if ((await archivedRows.first().getAttribute('class')).includes('hidden')) throw new Error('terminated row did not show after toggle');
    }
    await page.goto('http://127.0.0.1:18765/applications', { waitUntil: 'networkidle' });
    const manage = page.locator('[data-open-app]').first();
    if (await manage.count()) {
      await manage.click();
      if ((await page.locator('.manage-panel').first().getAttribute('class')).includes('hidden')) throw new Error('management panel did not open');
    }
    await page.goto('http://127.0.0.1:18765/interviews', { waitUntil: 'networkidle' });
    const reviewGroups = page.locator('.review-group');
    if (await reviewGroups.count()) {
      if (!(await reviewGroups.first().getAttribute('open') !== null)) throw new Error('latest review group should be open');
    }
    await page.goto('http://127.0.0.1:18765/resumes', { waitUntil: 'networkidle' });
    if (!(await page.locator('#resumeArchive').count())) throw new Error('resume archive is missing');
    await page.close();
  }
  await browser.close();
  if (consoleErrors.length) throw new Error(consoleErrors.join('\n'));
  if (!keepScreenshots && !process.env.QA_SCREENSHOT_DIR) {
    fs.rmSync(outputDir, { recursive: true, force: true });
  }
  console.log('Gateway UI QA passed: 5 routes × 2 viewports, interactions OK.');
})();

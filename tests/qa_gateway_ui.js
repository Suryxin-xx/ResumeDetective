const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const baseUrl = process.env.QA_GATEWAY_URL || 'http://127.0.0.1:18765';

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
  ]) {
    const page = await browser.newPage({ viewport: viewport });
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(`${viewport.name}: ${msg.text()}`); });
    page.on('pageerror', error => consoleErrors.push(`${viewport.name}: ${error.message}`));
    for (const route of ['/', '/board', '/applications', '/tasks', '/interviews', '/resumes', '/settings']) {
      await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
      if (overflow) throw new Error(`${viewport.name} ${route}: page-level horizontal overflow`);
      const name = route === '/' ? 'overview' : route.slice(1);
      await page.screenshot({ path: `${outputDir}/${viewport.name}-${name}.png`, fullPage: true });
    }
    await page.goto(`${baseUrl}/board`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: '表格' }).click();
    if (!(await page.locator('#boardView').getAttribute('class')).includes('hidden')) throw new Error('board view did not hide');
    if ((await page.locator('#tableView').getAttribute('class')).includes('hidden')) throw new Error('table view did not show');
    const archivedRows = page.locator('#boardTableRows tr[data-archived="1"]');
    if (await archivedRows.count()) {
      if (!(await archivedRows.first().getAttribute('class')).includes('hidden')) throw new Error('terminated row should be hidden by default');
      await page.locator('#toggleTerminated').click();
      if ((await archivedRows.first().getAttribute('class')).includes('hidden')) throw new Error('terminated row did not show after toggle');
    }
    await page.goto(`${baseUrl}/applications`, { waitUntil: 'networkidle' });
    const manage = page.locator('[data-open-app]').first();
    if (await manage.count()) {
      await manage.click();
      const appRow = page.locator('.application-row').first();
      const editorRow = appRow.locator('xpath=following-sibling::tr[1]');
      if (!(await editorRow.isVisible())) throw new Error('inline management row did not open');
      if (!(await editorRow.locator('select[name="stage_state"]').isVisible())) throw new Error('stage state selector is missing');
      if (!(await editorRow.locator('input[name="job_category"]').isVisible())) throw new Error('job category field is missing');
      await editorRow.locator('select[name="status"]').selectOption({ label: 'HR 面' });
      await page.waitForTimeout(50);
      if (!(await page.content()).includes('rdStageSync')) throw new Error('stage sync script is missing');
      if ((await editorRow.locator('select[name="stage_state"]').inputValue()) !== '待处理') throw new Error('new stage did not default to pending');
      await page.screenshot({ path: `${outputDir}/${viewport.name}-applications-inline.png`, fullPage: true });
    }
    await page.goto(`${baseUrl}/interviews`, { waitUntil: 'networkidle' });
    const reviewGroups = page.locator('.review-group');
    if (await reviewGroups.count()) {
      if (!(await reviewGroups.first().getAttribute('open') !== null)) throw new Error('latest review group should be open');
    }
    await page.goto(`${baseUrl}/resumes`, { waitUntil: 'networkidle' });
    if (!(await page.locator('#resumeArchive').count())) throw new Error('resume archive is missing');
    if (!(await page.locator('#resumeCategory').isVisible())) throw new Error('resume category filter is missing');
    await page.goto(`${baseUrl}/settings`, { waitUntil: 'networkidle' });
    if (!(await page.locator('input[name="workspace_title"]').isVisible())) throw new Error('workspace title setting is missing');
    if (!(await page.locator('input[name="automatic_backup_enabled"]').isVisible())) throw new Error('automatic backup setting is missing');
    if (await page.locator('input[name="developer_name"], input[name="contact_email"]').count()) throw new Error('fixed branding is still editable');
    if (!(await page.getByText('Suryxin-xx', { exact: true }).isVisible())) throw new Error('developer identity is missing');
    if (!(await page.locator('a[href="https://github.com/Suryxin-xx/ResumeDetective"]').first().isVisible())) throw new Error('project link is missing');
    await page.close();
  }
  await browser.close();
  if (consoleErrors.length) throw new Error(consoleErrors.join('\n'));
  if (!keepScreenshots && !process.env.QA_SCREENSHOT_DIR) {
    fs.rmSync(outputDir, { recursive: true, force: true });
  }
  console.log('Gateway UI QA passed: 7 desktop routes, interactions OK.');
})();

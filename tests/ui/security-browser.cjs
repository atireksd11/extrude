// Requires Playwright and Chromium; start local Uvicorn before running.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium'});
  const page = await browser.newPage({bypassCSP: true});
  const base = process.env.SECURITY_TEST_URL || 'http://127.0.0.1:8765';
  const token = 'synthetic-test-token-' + 'x'.repeat(32);
  const payload = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>';
  const calls = [];
  await page.route('**/v1/github/repositories', route => {
    calls.push(route.request().headers());
    if (route.request().headers().authorization !== `Bearer ${token}`) {
      return route.fulfill({status: 401, json: {detail: 'Shared access token required.'}});
    }
    return route.fulfill({json: [{id: 'a'.repeat(32), source: payload, url: 'https://github.com/example/public', head: 'b'.repeat(40)}]});
  });
  await page.route('**/v1/github/repositories/**', route => route.fulfill({json: {commits: [], files: [], inventory: {files: [], total: 0}, changes: {files: [], total: 0}, head_sha: 'b'.repeat(40), base_sha: null, audit: null}}));
  await page.goto(base + '/projects/github');
  await page.getByLabel('Access token').fill(token);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
  await page.waitForFunction(() => document.body.textContent.includes('<img src=x'));
  assert.equal(await page.evaluate(() => window.__xss), undefined);
  assert.equal(await page.locator('img[src="x"]').count(), 0);
  assert(calls.some(headers => headers.authorization === `Bearer ${token}`));
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  assert.equal((await page.context().cookies()).length, 0);
  assert(!page.url().includes(token));
  let leaked;
  let externalSeen = false;
  await page.route('https://external.example/**', route => { externalSeen = true; leaked = route.request().headers().authorization; return route.fulfill({body: 'ok', headers: {'Access-Control-Allow-Origin': '*'}}); });
  await page.evaluate(() => fetch('https://external.example/v1/test'));
  assert(externalSeen);
  assert.equal(leaked, undefined);
  await page.reload();
  await page.getByLabel('Access token').waitFor();
  console.log('PASS shared token retry, page-memory-only token, reload clears token, XSS rendered as text');
  await browser.close();
})().catch(error => {console.error(error); process.exit(1);});

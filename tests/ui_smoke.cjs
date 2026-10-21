/* Optional browser smoke test. Requires Playwright and a fresh running backend.
 * It confirms one synthetic 50,000 IQD transfer. Never use against real data.
 * READY_CHROMIUM_EXECUTABLE can select an installed Chrome binary.
 */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.READY_CHROMIUM_EXECUTABLE ? { executablePath: process.env.READY_CHROMIUM_EXECUTABLE } : {}),
  });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  try {
    await page.goto('http://127.0.0.1:8765', { waitUntil: 'networkidle' });
    await page.locator('#chat-input').fill('حول ٥٠ ألف لعلي');
    await page.locator('#send-button').click();
    await page.getByRole('button', { name: 'علي ضياء', exact: true }).click();
    await page.locator('[data-confirm-draft]').waitFor();
    assert.match(await page.locator('.draft-details').innerText(), /علي ضياء/);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    if (process.env.READY_UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.READY_UI_SCREENSHOT_DIR}/ready_mobile_review.png`, fullPage: true });
    const before = await page.locator('#account-heading').innerText();
    await page.locator('#chat-input').fill('نعم');
    await page.locator('#send-button').click();
    await page.getByRole('button', { name: 'استئناف مراجعة عملية', exact: true }).click();
    assert.equal(await page.locator('#account-heading').innerText(), before);
    await page.locator('[data-confirm-draft]').click();
    await page.locator('.receipt-card').waitFor();
    assert.notEqual(await page.locator('#account-heading').innerText(), before);
    assert.match(await page.locator('.receipt-card').innerText(), /SUCCEEDED/);
    await page.locator('.support-trigger').click();
    await page.locator('#support-issue').fill('المستلم يقول المبلغ بعده ما وصله');
    await page.getByRole('button', { name: 'عرض مسودة الدعم', exact: true }).click();
    await page.locator('.support-copy').waitFor();
    assert.match(await page.locator('.support-copy').inputValue(), /SUCCEEDED/);
    assert.match(await page.locator('#active-area').innerText(), /ما انرسلت/);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    if (process.env.READY_UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.READY_UI_SCREENSHOT_DIR}/ready_mobile_support.png`, fullPage: true });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.locator('#action-list [data-action-id="VIEW_WALLET_INSIGHTS"]').click();
    await page.locator('.source-evidence').waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    if (process.env.READY_UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.READY_UI_SCREENSHOT_DIR}/ready_desktop_insights.png`, fullPage: true });
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ result: 'PASS', mobile: '390x844', desktop: '1280x900', checked: ['ambiguous recipient', 'review', 'typed yes cannot confirm', 'explicit confirmation', 'balance refresh', 'stored receipt', 'unsent support draft', 'source-linked insights', 'no horizontal overflow', 'no JavaScript errors'] }, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exit(1); });

/**
 * Record E2E with Chrome fake media devices (no real mic hardware required).
 * Still exercises Record UI → MediaRecorder → createAnalysis → Result.
 */
import { chromium } from 'playwright';

const BASE = process.env.VAGENT_WEB_BASE || 'http://127.0.0.1:5173';

async function main() {
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  });
  const context = await browser.newContext();
  await context.grantPermissions(['microphone'], { origin: BASE });
  const page = await context.newPage();
  const apiLog = [];
  page.on('response', async (res) => {
    const u = res.url();
    if (u.includes('/v1/')) {
      const entry = { method: res.request().method(), url: u, status: res.status() };
      if (res.request().method() === 'POST' && u.includes('/v1/analyses') && res.status() < 400) {
        try {
          entry.body = await res.json();
        } catch {
          /* ignore */
        }
      }
      apiLog.push(entry);
    }
  });
  const report = {
    RECORD: 'FAIL',
    RECORD_PLAY: 'FAIL',
    RECORD_SEEK: 'FAIL',
    RECORD_ANALYZE: 'FAIL',
    RESULT: 'FAIL',
    POST_STATUS: null,
    analysis_id: null,
    final_status: null,
    API_500: 0,
    errors: [],
  };

  try {
    await page.goto(BASE + '/record', { waitUntil: 'networkidle' });
    // accompaniment OFF by default
    const startBtn = page.getByRole('button', { name: /녹음 시작|시작/i });
    await startBtn.click();
    // wait past MIN_SEC (15)
    await page.waitForTimeout(16500);
    const stopBtn = page.getByRole('button', { name: /녹음 종료|종료|Stop/i });
    await stopBtn.click();
    await page.waitForSelector('input[type="range"]', { timeout: 20000 });
    report.RECORD = 'PASS';

    const playBtn = page.getByRole('button', { name: /재생|일시정지/ });
    if (await playBtn.count()) {
      await playBtn.first().click();
      await page.waitForTimeout(500);
      report.RECORD_PLAY = 'PASS';
    }
    const range = page.locator('input[type="range"]').first();
    await range.evaluate((el) => {
      const max = Number(el.max || 10);
      el.value = String(Math.min(max, 5));
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
    report.RECORD_SEEK = 'PASS';

    await page.getByRole('button', { name: /분석하기/ }).click();
    await page.waitForURL(/analyzing|result/, { timeout: 30000 });
    report.RECORD_ANALYZE = 'PASS';

    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      const post = apiLog.find((x) => x.method === 'POST' && x.url.includes('/v1/analyses'));
      if (post) {
        report.POST_STATUS = post.status;
        report.analysis_id = post.body?.analysis_id || null;
      }
      if (page.url().includes('/result/')) break;
      await page.waitForTimeout(1000);
    }
    if (page.url().includes('/result/') && report.analysis_id) {
      report.RESULT = 'PASS';
      const jobRes = await page.request.get(`${BASE}/v1/analyses/${report.analysis_id}`, {
        headers: { 'X-VAgent-User-Key': 'demo-user', 'X-User-Id': 'demo-user' },
      });
      const job = await jobRes.json();
      report.final_status = job.status;
    } else {
      report.errors.push('result_timeout:' + page.url());
    }
    report.API_500 = apiLog.filter((x) => x.status >= 500).length;
    console.log(JSON.stringify({ report, apiLog: apiLog.slice(0, 20) }, null, 2));
    if (report.RESULT !== 'PASS' || report.API_500 > 0) process.exitCode = 1;
  } catch (e) {
    report.errors.push(String(e));
    console.log(JSON.stringify({ report, apiLog }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main();

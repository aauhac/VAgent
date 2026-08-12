/**
 * Real Chrome upload E2E for VAgent Production Gate v2.
 * Record mic flow is intentionally NOT automated (human mic permission).
 */
import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.VAGENT_WEB_BASE || 'http://127.0.0.1:5173';
const WAV = process.env.VAGENT_E2E_WAV || path.resolve(__dirname, '../runtime/_e2e_upload.wav');

function parseMultipartFields(postData, contentType) {
  const out = {};
  if (!postData || !contentType) return out;
  const m = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType);
  if (!m) return out;
  const boundary = m[1] || m[2];
  const parts = String(postData).split(`--${boundary}`);
  for (const part of parts) {
    const nameMatch = /name="([^"]+)"/i.exec(part);
    if (!nameMatch) continue;
    const name = nameMatch[1];
    const idx = part.indexOf('\r\n\r\n');
    if (idx < 0) continue;
    let value = part.slice(idx + 4);
    value = value.replace(/\r\n$/, '').replace(/--$/, '').trim();
    // skip binary file bodies
    if (name === 'file' || value.length > 200) {
      out[name] = value.length > 200 ? `[binary ${value.length} chars]` : value;
      continue;
    }
    out[name] = value;
  }
  return out;
}

async function main() {
  if (!fs.existsSync(WAV)) throw new Error(`missing wav: ${WAV}`);
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  const apiLog = [];
  const postBodies = [];

  page.on('request', (req) => {
    const u = req.url();
    if (req.method() === 'POST' && u.includes('/v1/analyses')) {
      const ct = req.headers()['content-type'] || '';
      const raw = req.postData();
      const fields = parseMultipartFields(raw, ct);
      postBodies.push({ url: u, fields, hasPostData: !!raw });
    }
  });

  page.on('response', async (res) => {
    const u = res.url();
    if (u.includes('/v1/') || u.includes('/health')) {
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

  const consoleErrors = [];
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  const report = {
    REAL_CHROME: true,
    HOME: 'FAIL',
    UPLOAD: 'FAIL',
    UPLOAD_PLAY: 'FAIL',
    UPLOAD_SEEK: 'FAIL',
    UPLOAD_ANALYZE: 'FAIL',
    RESULT: 'FAIL',
    HISTORY: 'FAIL',
    MIXED: 'FAIL',
    VOCAL_ONLY_NETWORK: false,
    MIXED_NETWORK: false,
    VOCAL_ONLY_FIELDS: null,
    MIXED_FIELDS: null,
    API_500: 0,
    history_calls: 0,
    access_burst: 0,
    errors: [],
  };

  try {
    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    report.HOME = 'PASS';

    await page.goto(BASE + '/upload', { waitUntil: 'networkidle' });
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(WAV);
    await page.waitForSelector('input[type="range"]', { timeout: 20000 });
    report.UPLOAD = 'PASS';

    // Play
    const playBtn = page.locator('button[aria-label="재생"], button[aria-label="일시정지"]').first();
    if (await playBtn.count()) {
      await playBtn.click();
      await page.waitForTimeout(800);
      report.UPLOAD_PLAY = 'PASS';
    } else {
      const alt = page.getByRole('button', { name: /재생|Play/i });
      if (await alt.count()) {
        await alt.first().click();
        report.UPLOAD_PLAY = 'PASS';
      } else {
        report.errors.push('play_button_missing');
      }
    }

    // Seek via range
    const range = page.locator('input[type="range"]').first();
    await range.evaluate((el) => {
      const max = Number(el.max || 10);
      const target = Math.min(max, Math.max(1, max * 0.4));
      el.value = String(target);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForTimeout(400);
    report.UPLOAD_SEEK = 'PASS';

    // Analyze VOCAL_ONLY
    await page.getByRole('button', { name: /분석하기/ }).click();
    await page.waitForURL(/analyzing|result/, { timeout: 30000 });
    report.UPLOAD_ANALYZE = 'PASS';

    // Capture first analysis id + poll job for input_mode (multipart body often unavailable)
    let vocalAnalysisId = null;
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      if (!vocalAnalysisId) {
        const postOk = apiLog.find(
          (x) => x.method === 'POST' && x.url.includes('/v1/analyses') && x.status === 200 && x.body?.analysis_id,
        );
        if (postOk) vocalAnalysisId = postOk.body.analysis_id;
      }
      if (page.url().includes('/result/')) break;
      await page.waitForTimeout(1000);
    }
    if (page.url().includes('/result/')) {
      report.RESULT = 'PASS';
    } else {
      report.errors.push('result_url_timeout:' + page.url());
    }
    if (vocalAnalysisId) {
      try {
        const jobRes = await page.request.get(`${BASE}/v1/analyses/${vocalAnalysisId}`, {
          headers: { 'X-VAgent-User-Key': 'demo-user', 'X-User-Id': 'demo-user' },
        });
        const job = await jobRes.json();
        report.VOCAL_ONLY_FIELDS = {
          analysis_id: vocalAnalysisId,
          input_mode: job.input_mode,
          analysis_mode: job.analysis_mode,
          status: job.status,
        };
        report.VOCAL_ONLY_NETWORK =
          String(job.input_mode || '').toUpperCase() === 'VOCAL_ONLY' && jobRes.status() === 200;
      } catch (e) {
        report.errors.push('vocal_job_fetch:' + String(e));
      }
    }

    // History
    const beforeHist = apiLog.length;
    await page.goto(BASE + '/history', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    const histSlice = apiLog.slice(beforeHist);
    report.history_calls = histSlice.filter((x) => x.url.includes('/v1/history')).length;
    report.access_burst = histSlice.filter(
      (x) => x.method === 'GET' && /\/analyses\/[^/]+\/access/.test(x.url),
    ).length;
    if (report.history_calls >= 1 && report.access_burst === 0) {
      report.HISTORY = 'PASS';
    } else if (report.history_calls >= 1) {
      report.HISTORY = 'FAIL';
      report.errors.push(`access_burst=${report.access_burst}`);
    } else {
      report.errors.push('no_history_call');
    }

    // MIXED upload
    await page.goto(BASE + '/upload', { waitUntil: 'networkidle' });
    const toggle = page.locator('input[type="checkbox"]').first();
    if (await toggle.count()) await toggle.check();
    await fileInput.setInputFiles(WAV);
    await page.waitForSelector('input[type="range"]', { timeout: 20000 });
    const beforeMixedLog = apiLog.length;
    await page.getByRole('button', { name: /분석하기/ }).click();
    await page.waitForTimeout(4000);
    const mixedPost = apiLog
      .slice(beforeMixedLog)
      .find((x) => x.method === 'POST' && x.url.includes('/v1/analyses') && x.status === 200);
    if (mixedPost?.body?.analysis_id) {
      try {
        const jobRes = await page.request.get(`${BASE}/v1/analyses/${mixedPost.body.analysis_id}`, {
          headers: { 'X-VAgent-User-Key': 'demo-user', 'X-User-Id': 'demo-user' },
        });
        const job = await jobRes.json();
        report.MIXED_FIELDS = {
          analysis_id: mixedPost.body.analysis_id,
          input_mode: job.input_mode,
          analysis_mode: job.analysis_mode,
          status: job.status,
        };
        // Backend policy: FUNCTIONAL + MIXED => separate=true (enforced server-side)
        const ok = String(job.input_mode || '').toUpperCase() === 'MIXED';
        report.MIXED = ok ? 'PASS' : 'FAIL';
        report.MIXED_NETWORK = ok;
        if (!ok) report.errors.push('mixed_job:' + JSON.stringify(job));
      } catch (e) {
        report.errors.push('mixed_job_fetch:' + String(e));
      }
    } else {
      report.errors.push('no_mixed_post_200');
    }

    report.API_500 = apiLog.filter((x) => x.status >= 500).length;

    console.log(JSON.stringify({ report, apiLog, postBodies, consoleErrors }, null, 2));
    if (report.API_500 > 0 || report.RESULT !== 'PASS' || report.UPLOAD !== 'PASS') {
      process.exitCode = 1;
    }
  } catch (e) {
    report.errors.push(String(e));
    console.log(JSON.stringify({ report, apiLog, postBodies, consoleErrors }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main();

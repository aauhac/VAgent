/**
 * Mobile visual smoke for Detail / Precision / diagnostic flow.
 * Uses QA Vite harness (qa-visual.html) — no production deploy.
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'qa_output', 'detail_precision_ux', 'screenshots');
const BASE = process.env.QA_VISUAL_BASE || 'http://127.0.0.1:5177';
const ANALYSIS = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const SPARSE = 'cccccccccccccccccccccccccccccccc';
const SESSION = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const TASK = 'comfortable_glide';

const VIEWPORTS = [
  { name: '375x812', width: 375, height: 812 },
  { name: '390x844', width: 390, height: 844 },
  { name: '430x932', width: 430, height: 932 },
];

const ROUTES = [
  { id: 'detail', hash: `#/result/${ANALYSIS}/detail` },
  { id: 'detail-1axis', hash: `#/result/${SPARSE}/detail` },
  { id: 'unlock', hash: `#/premium?analysis=${ANALYSIS}` },
  { id: 'concern', hash: `#/diagnostic/${SESSION}/concerns` },
  { id: 'safety', hash: `#/diagnostic/${SESSION}/safety` },
  { id: 'recordings', hash: `#/diagnostic/${SESSION}/recordings` },
  { id: 'task', hash: `#/diagnostic/${SESSION}/task/${TASK}` },
  { id: 'precision', hash: `#/diagnostic/${SESSION}/report` },
];

const BANNED = [
  '개발 환경 Mock 결제',
  '실제 과금이 아닙니다',
  '내 연습 목표',
  '목표 바꾸기',
  '무엇부터 연습',
  '단계별 연습',
  'Task 불러오는 중',
  '업그레이드 요금',
  '측정 근거 부족',
  '판단 근거 부족',
];

function wait(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function ensureServer() {
  try {
    const res = await fetch(`${BASE}/qa-visual.html`);
    if (res.ok) return null;
  } catch {
    /* start */
  }
  const child = spawn(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    ['vite', '--config', 'vite.qa-visual.config.ts', '--host', '127.0.0.1', '--port', '5177'],
    { cwd: path.join(ROOT, 'miniapp'), stdio: 'pipe', shell: true },
  );
  for (let i = 0; i < 40; i += 1) {
    await wait(500);
    try {
      const res = await fetch(`${BASE}/qa-visual.html`);
      if (res.ok) return child;
    } catch {
      /* retry */
    }
  }
  throw new Error('QA visual server failed to start');
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const child = await ensureServer();
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const report = [];
  try {
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 2,
      });
      const page = await context.newPage();
      for (const route of ROUTES) {
        const url = `${BASE}/qa-visual.html${route.hash}`;
        await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForFunction(() => document.documentElement.dataset.visualReady === '1', null, { timeout: 8000 }).catch(() => {});
        await wait(400);
        const header = await page.locator('[data-testid="sub-page-header"]').count();
        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return Math.max(0, doc.scrollWidth - doc.clientWidth);
        });
        const body = await page.locator('body').innerText();
        const bannedHits = BANNED.filter((t) => body.includes(t));
        const title = await page.locator('.sub-page-header__title').textContent().catch(() => '');
        const file = `${route.id}-${vp.name}.png`;
        await page.screenshot({ path: path.join(OUT, file), fullPage: false });
        const row = {
          route: route.id,
          viewport: vp.name,
          header,
          overflow,
          title: (title || '').trim(),
          bannedHits,
          pass: header === 1 && overflow === 0 && bannedHits.length === 0,
        };
        report.push(row);
        console.log(JSON.stringify(row));
      }
      await context.close();
    }
  } finally {
    await browser.close();
    if (child) child.kill();
  }
  const outJson = path.join(ROOT, 'qa_output', 'detail_precision_ux', 'visual_smoke.json');
  fs.mkdirSync(path.dirname(outJson), { recursive: true });
  fs.writeFileSync(outJson, JSON.stringify(report, null, 2));
  const failed = report.filter((r) => !r.pass);
  if (failed.length) {
    console.error(`FAIL ${failed.length}/${report.length}`);
    process.exit(1);
  }
  console.log(`PASS ${report.length}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

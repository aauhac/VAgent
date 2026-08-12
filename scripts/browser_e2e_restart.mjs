import { chromium } from 'playwright';
const BASE = 'http://127.0.0.1:5173';
const aid = '6ea4b551d067470b90d4adf5f28f74a0';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
const api = [];
let s500 = 0;
page.on('response', r => {
  if (r.url().includes('/v1/')) {
    api.push({ m: r.request().method(), u: r.url(), s: r.status() });
    if (r.status() >= 500) s500++;
  }
});
await page.goto(BASE + '/history', { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
const histOk = api.some(x => x.u.includes('/v1/history') && x.s === 200);
await page.goto(BASE + '/result/' + aid, { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);
const resultOk = page.url().includes('/result/');
const analysisOk = api.some(x => x.u.includes('/analyses/' + aid) && x.s === 200);
console.log(JSON.stringify({ RESTART_BROWSER: true, HISTORY: histOk ? 'PASS' : 'FAIL', RESULT: resultOk && analysisOk ? 'PASS' : 'FAIL', API_500: s500, api: api.slice(-15) }, null, 2));
await browser.close();

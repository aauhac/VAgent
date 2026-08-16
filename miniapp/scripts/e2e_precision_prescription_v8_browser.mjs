/**
 * Prescription-First Coaching v8 — static + optional live browser checks.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const WEB = process.env.VAGENT_E2E_WEB || 'http://127.0.0.1:5173';
const outPath = path.join(ROOT, `.e2e_precision_prescription_v8_${Date.now()}.json`);

async function main() {
  const result = {
    ok: false,
    versions: {},
    prescriptionBlock: null,
    comparisonHiddenNormally: null,
    live: null,
    error: null,
  };

  const versionsTs = fs.readFileSync(path.join(ROOT, 'miniapp/src/lib/reportVersions.ts'), 'utf8');
  result.versions.qa = versionsTs.includes('precision-qa-prescription-first-v8');
  result.versions.report = versionsTs.includes('precision-report-v9');

  const premium = fs.readFileSync(path.join(ROOT, 'miniapp/src/pages/PremiumReport.tsx'), 'utf8');
  result.prescriptionBlock = premium.includes('PrescriptionBlock');
  result.comparisonHiddenNormally =
    premium.includes('showDebug')
    && premium.includes('QAComparisonBlock')
    && /showDebug\s*\?\s*\([\s\S]*QAComparisonBlock/.test(premium);

  const rx = fs.readFileSync(path.join(ROOT, 'miniapp/src/components/report/PrescriptionBlock.tsx'), 'utf8');
  const labels =
    rx.includes('이렇게 해보세요')
    && rx.includes('그래도 잘 안 되면')
    && rx.includes('잘 되고 있다는 신호')
    && rx.includes('원곡에서는');

  result.ok =
    result.versions.qa
    && result.versions.report
    && result.prescriptionBlock
    && result.comparisonHiddenNormally
    && labels;

  const sessionId = process.env.VAGENT_E2E_SESSION;
  if (sessionId) {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
      await page.goto(`${WEB}/diagnostic/${sessionId}/premium-report`, { waitUntil: 'networkidle' });
      const compareCount = await page.locator('text=비교해보기').count();
      const rxCount = await page.locator('[data-testid^="qa-rx-"]').count();
      const circled = await page.locator('text=①').count();
      result.live = {
        sessionId,
        compareVisible: compareCount > 0,
        prescriptionVisible: rxCount > 0,
        circledOneVisible: circled > 0,
      };
      result.ok = result.ok && compareCount === 0 && rxCount > 0;
    } catch (e) {
      result.error = String(e);
      result.ok = false;
    } finally {
      await browser.close();
    }
  }

  fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ wrote: outPath, ok: result.ok, live: result.live }, null, 2));
  process.exit(result.ok ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

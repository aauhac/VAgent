/**
 * QA Coaching Depth v7 + Report Coherence Lock — browser/static checks.
 * Writes: .e2e_precision_coaching_v7_<ts>.json
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const API = process.env.VAGENT_E2E_API || 'http://127.0.0.1:8000';
const WEB = process.env.VAGENT_E2E_WEB || 'http://127.0.0.1:5173';
const outPath = path.join(ROOT, `.e2e_precision_coaching_v7_${Date.now()}.json`);

async function main() {
  const result = {
    ok: false,
    versions: {},
    protocolCardInSource: null,
    legacyGated: null,
    hasProtocolStepsGuard: null,
    live: null,
    error: null,
  };

  const versionsTs = fs.readFileSync(path.join(ROOT, 'miniapp/src/lib/reportVersions.ts'), 'utf8');
  result.versions.qa = versionsTs.includes('precision-qa-coaching-depth-v7');
  result.versions.report = versionsTs.includes('precision-report-v8');

  const premium = fs.readFileSync(path.join(ROOT, 'miniapp/src/pages/PremiumReport.tsx'), 'utf8');
  result.protocolCardInSource = premium.includes('CoachingProtocolCard') && premium.includes('hasProtocolSteps');
  result.legacyGated = premium.includes('!hasProtocolSteps');
  result.hasProtocolStepsGuard = premium.includes('rawProtocol.steps.length > 0');

  const card = fs.readFileSync(path.join(ROOT, 'miniapp/src/components/report/CoachingProtocolCard.tsx'), 'utf8');
  const cardLabels =
    card.includes('이번에 먼저 해볼 것')
    && card.includes('잘 되면')
    && card.includes('잘 안 되면')
    && (card.includes('원곡') || card.includes('노래에 적용'));

  result.ok =
    result.versions.qa
    && result.versions.report
    && result.protocolCardInSource
    && result.legacyGated
    && result.hasProtocolStepsGuard
    && cardLabels;

  const sessionId = process.env.VAGENT_E2E_SESSION;
  if (sessionId) {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
      await page.goto(`${WEB}/diagnostic/${sessionId}/premium-report`, { waitUntil: 'networkidle' });
      const protocolVisible = (await page.locator('[data-testid="coaching-protocol"]').count()) > 0;
      const legacyOnly =
        (await page.locator('[data-testid="practice-section"]').count()) > 0 && !protocolVisible;
      result.live = { protocolVisible, legacyOnly, sessionId };
      result.ok = result.ok && protocolVisible && !legacyOnly;
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

/**
 * Coaching UX Polish v9 — static + optional live browser checks.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const WEB = process.env.VAGENT_E2E_WEB || 'http://127.0.0.1:5173';
const outPath = path.join(ROOT, `.e2e_precision_coaching_ux_v9_${Date.now()}.json`);

async function main() {
  const result = {
    ok: false,
    versions: {},
    ui: {},
    language: {},
    live: null,
    error: null,
  };

  const versionsTs = fs.readFileSync(path.join(ROOT, 'miniapp/src/lib/reportVersions.ts'), 'utf8');
  result.versions.qa = versionsTs.includes('precision-qa-coaching-ux-v9');
  result.versions.report = versionsTs.includes('precision-report-v10');

  const premium = fs.readFileSync(path.join(ROOT, 'miniapp/src/pages/PremiumReport.tsx'), 'utf8');
  result.ui.priorityCompact = premium.includes('우선 포인트 ·');
  result.ui.whyLabel = premium.includes('왜 이 연습?');
  result.ui.comparisonDebugOnly =
    premium.includes('showDebug')
    && /showDebug\s*\?\s*\([\s\S]*QAComparisonBlock/.test(premium);

  const scrub = fs.readFileSync(path.join(ROOT, 'miniapp/src/lib/reportPresentation.ts'), 'utf8');
  result.language.scrubPitch = scrub.includes("pitch") && scrub.includes('음높이');
  result.language.scrubPhrase = scrub.includes('구절');
  result.language.scrubGlide = scrub.includes('이어 올리기');

  const protocolPy = fs.readFileSync(
    path.join(ROOT, 'audio_analyzer/diagnostic/coaching_protocol.py'),
    'utf8',
  );
  result.ui.directBrightTitle = protocolPy.includes('발음으로 선명함 만들기');
  result.ui.noShortCompare = !protocolPy.includes('짧은 비교');

  result.ok =
    result.versions.qa
    && result.versions.report
    && result.ui.priorityCompact
    && result.ui.whyLabel
    && result.ui.comparisonDebugOnly
    && result.ui.directBrightTitle
    && result.ui.noShortCompare
    && result.language.scrubPitch
    && result.language.scrubPhrase
    && result.language.scrubGlide;

  const sessionId = process.env.VAGENT_E2E_SESSION;
  if (sessionId) {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
      await page.goto(`${WEB}/diagnostic/${sessionId}/premium-report`, { waitUntil: 'networkidle' });
      const body = await page.locator('body').innerText();
      const banned = ['비교해보기', '짧은 비교', 'pitch', 'phrase', 'glide', 'sustain'];
      const hits = Object.fromEntries(banned.map((b) => [b, body.toLowerCase().includes(b.toLowerCase())]));
      const hasDirect =
        body.includes('발음으로 선명함 만들기')
        || body.includes('이렇게 해보세요')
        || body.includes('자음 시작');
      result.live = {
        sessionId,
        hits,
        hasDirect,
        hasAB: /\bA\b/.test(body) && /\bB\b/.test(body) && body.includes('비교'),
      };
      result.ok =
        result.ok
        && !hits['비교해보기']
        && !hits['짧은 비교']
        && !hits.pitch
        && !hits.phrase
        && !hits.glide
        && !hits.sustain
        && hasDirect
        && !result.live.hasAB;
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

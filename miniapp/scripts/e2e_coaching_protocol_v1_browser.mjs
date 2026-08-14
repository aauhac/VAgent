/**
 * Coaching Protocol v1 — static / optional live browser checks.
 * Writes .e2e_coaching_protocol_v1_<ts>.json
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const outPath = path.join(ROOT, `.e2e_coaching_protocol_v1_${Date.now()}.json`);

const result = {
  ok: false,
  entryVisible: false,
  progressionVisible: false,
  regressionVisible: false,
  songTransferVisible: false,
  mobileCss: false,
  regenerateHidden: false,
  error: null,
};

try {
  const card = fs.readFileSync(path.join(ROOT, 'miniapp/src/components/report/CoachingProtocolCard.tsx'), 'utf8');
  const premium = fs.readFileSync(path.join(ROOT, 'miniapp/src/pages/PremiumReport.tsx'), 'utf8');
  const css = fs.readFileSync(path.join(ROOT, 'miniapp/src/styles/app.css'), 'utf8');

  result.entryVisible = card.includes('이번에 먼저 해볼 것') && card.includes('data-testid="coaching-protocol"');
  result.progressionVisible = card.includes('잘 되면') && card.includes('다음 단계 보기');
  result.regressionVisible = card.includes('잘 안 되면');
  result.songTransferVisible = card.includes('노래에 적용') || card.includes('protocol-song-transfer');
  result.mobileCss = css.includes('.spectrum-label') && css.includes('white-space: nowrap');
  result.regenerateHidden = premium.includes('import.meta.env.DEV && showDebug');
  result.ok =
    result.entryVisible
    && result.progressionVisible
    && result.regressionVisible
    && result.songTransferVisible
    && result.regenerateHidden;

  fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ wrote: outPath, ok: result.ok }, null, 2));
  process.exit(result.ok ? 0 : 1);
} catch (e) {
  result.error = String(e?.message || e);
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
  console.error(result.error);
  process.exit(1);
}

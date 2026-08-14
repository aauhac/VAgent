/**
 * Precision Coaching Generalization v6 — profile UI / QA discrimination browser checks.
 *
 * Requires: API on :8000 and miniapp Vite (or set VAGENT_E2E_API / VAGENT_E2E_WEB).
 * Writes: .e2e_precision_coaching_v6_<ts>.json
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const API = process.env.VAGENT_E2E_API || 'http://127.0.0.1:8000';
const WEB = process.env.VAGENT_E2E_WEB || 'http://127.0.0.1:5173';
const outPath = path.join(ROOT, `.e2e_precision_coaching_v6_${Date.now()}.json`);

const AXIS_HELP = {
  contact: '가성·진성을 판정하지는',
  breath: '숨결이나 잡음',
  effort: '목 근육의 힘을 직접 측정',
  register: '자연스럽게 이어지는지',
  resonance: '중역대에서 소리의 중심',
};

async function main() {
  const result = {
    ok: false,
    tooltips: {},
    registerLayout: {},
    regenerateHidden: null,
    presenceDedup: null,
    qaGroups: {},
    screenshot: null,
    error: null,
  };

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

  try {
    // Prefer an existing session if env set; otherwise skip live report and only assert help module + static CSS
    const sessionId = process.env.VAGENT_E2E_SESSION;
    if (!sessionId) {
      result.error = 'VAGENT_E2E_SESSION not set — static checks only';
      const helpPath = path.join(ROOT, 'miniapp/src/lib/axisHelpText.ts');
      const helpSrc = fs.readFileSync(helpPath, 'utf8');
      for (const [k, needle] of Object.entries(AXIS_HELP)) {
        result.tooltips[k] = helpSrc.includes(needle) || helpSrc.includes(needle.slice(0, 8));
      }
      const css = fs.readFileSync(path.join(ROOT, 'miniapp/src/styles/app.css'), 'utf8');
      result.registerLayout = {
        labelNowrap: css.includes('.spectrum-label') && css.includes('white-space: nowrap'),
        mobileColumn: css.includes('flex-direction: column'),
        descriptionClass: css.includes('.spectrum-description'),
      };
      const premium = fs.readFileSync(path.join(ROOT, 'miniapp/src/pages/PremiumReport.tsx'), 'utf8');
      result.regenerateHidden = premium.includes('import.meta.env.DEV && showDebug');
      result.presenceDedup = helpSrc.includes('PRESENCE') && premium.includes('중역 존재감') === false
        ? 'check VocalProfile'
        : true;
      const vp = fs.readFileSync(path.join(ROOT, 'miniapp/src/lib/reportPresentation.ts'), 'utf8');
      result.presenceDedup = vp.includes("'중역 존재감'");
      result.ok =
        Object.values(result.tooltips).every(Boolean)
        && result.registerLayout.labelNowrap
        && result.regenerateHidden
        && result.presenceDedup;
      fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
      console.log(JSON.stringify({ wrote: outPath, ok: result.ok }, null, 2));
      await browser.close();
      process.exit(result.ok ? 0 : 1);
    }

    await page.goto(`${WEB}/diagnostic/${sessionId}/premium-report?debug=0`, { waitUntil: 'networkidle' });
    const regen = await page.locator('[data-testid="dev-regenerate-report"]').count();
    result.regenerateHidden = regen === 0;

    await page.goto(`${WEB}/diagnostic/${sessionId}/premium-report?debug=1`, { waitUntil: 'networkidle' });
    for (const label of ['접촉감', '숨 섞임', '힘', '성구 연결', '중역 존재감']) {
      const row = page.locator('.spectrum-axis', { hasText: label }).first();
      if (await row.count()) {
        const btn = row.locator('.spectrum-help-btn');
        if (await btn.count()) {
          await btn.click();
          const tip = row.locator('.spectrum-help-tip');
          result.tooltips[label] = (await tip.count()) > 0 && ((await tip.textContent()) || '').length > 10;
          await page.keyboard.press('Escape');
        }
      }
    }

    const regLabel = page.locator('.spectrum-axis', { hasText: '성구 연결' }).locator('.spectrum-label').first();
    if (await regLabel.count()) {
      const box = await regLabel.boundingBox();
      result.registerLayout = {
        height: box?.height ?? null,
        width: box?.width ?? null,
        verticalBreak: box ? box.height > 28 : null,
      };
      const shot = path.join(ROOT, `.e2e_register_axis_390_${Date.now()}.png`);
      await page.locator('.spectrum-axis', { hasText: '성구 연결' }).first().screenshot({ path: shot });
      result.screenshot = shot;
    }

    const presenceCount = await page.locator('.spectrum-label', { hasText: '중역 존재감' }).count();
    const legacyResonance = await page.locator('.spectrum-label', { hasText: '공명 존재감' }).count();
    result.presenceDedup = presenceCount <= 1 && legacyResonance === 0;

    result.ok =
      result.regenerateHidden
      && Object.values(result.tooltips).filter(Boolean).length >= 3
      && result.registerLayout.verticalBreak === false
      && result.presenceDedup;

    fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
    console.log(JSON.stringify({ wrote: outPath, ok: result.ok, api: API }, null, 2));
  } catch (e) {
    result.error = String(e?.message || e);
    fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
    console.error(result.error);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main();

/**
 * User-facing vocabulary + Result UX simplification tests (Vitest-compatible assertions via node).
 * Run with: npx --yes tsx miniapp/scripts/check_result_ux_copy.mts
 */
import assert from 'node:assert/strict';
import {
  buildAxisChangeCopy,
  containsIgaPlaceholder,
  containsRawUserFacingToken,
  howMuchStableSummary,
  recentWindowLabel,
  scrubRawTokensFromUserText,
  stateLabelKo,
  unresolvedLabelKo,
} from '../src/lib/userFacingLabels.ts';
import { buildLocalProgressInsight } from '../src/lib/progressPresentation.ts';
import { diagnosticOfferBullets } from '../src/lib/diagnosticOffer.ts';
import { diagnosisFromPrimary } from '../src/lib/reportPresentation.ts';

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (e) {
    console.error(`FAIL - ${name}`);
    throw e;
  }
}

test('progress labels are Korean', () => {
  assert.equal(stateLabelKo('STABLE'), '안정적인 편');
  assert.equal(stateLabelKo('FIRM'), '단단한 편');
  assert.equal(stateLabelKo('CONNECTED'), '자연스럽게 연결되는 편');
});

test('one history does not say recent five', () => {
  assert.ok(!howMuchStableSummary(1, 1).includes('최근 5회'));
  assert.equal(recentWindowLabel(1), '이전 기록');
  assert.equal(recentWindowLabel(3), '최근 3회');
  assert.equal(recentWindowLabel(5), '최근 5회');
});

test('change copy has no 이(가)', () => {
  const t = buildAxisChangeCopy('effort', 'MODERATE', 'LOW');
  assert.ok(!containsIgaPlaceholder(t));
  assert.ok(t.includes('힘을 덜 쓰는'));
});

test('contact change natural', () => {
  const t = buildAxisChangeCopy('contact', 'FIRM', 'MID');
  assert.ok(!containsIgaPlaceholder(t));
  assert.ok(!t.includes('FIRM'));
});

test('local insight how_much uses actual count', () => {
  const out = buildLocalProgressInsight(
    { register_connection: 'CONNECTED' },
    [{ canonical: { register_connection: 'PARTIAL' } }],
    { goal: 'REGISTER_CONNECTION', recentN: 5 },
  );
  const cards = [...out.improved, ...out.changed, ...out.maintained];
  for (const c of cards) {
    assert.ok(!(c.how_much?.summary || '').includes('최근 5회'));
  }
});

test('diagnostic labels korean', () => {
  const bullets = diagnosticOfferBullets({
    unresolved_labels: ['REGISTER_CONNECTION', 'BREATHINESS', 'CONTACT'],
  });
  const joined = bullets.join(' ');
  assert.ok(!joined.includes('REGISTER_CONNECTION'));
  assert.ok(joined.includes('성구 연결'));
  assert.ok(joined.includes('숨 섞임'));
});

test('finding does not say effort token', () => {
  const d = diagnosisFromPrimary({
    id: 'GENERAL_EXCESS_EFFORT',
    effort_assessment: { global_severity: 'HIGH', context_note: '여러 구간에서 effort 관련 패턴' },
  });
  assert.ok(d);
  assert.ok(!/\beffort\b/i.test(d!.title));
  assert.ok(!/\beffort\b/i.test(d!.detail));
  assert.ok(d!.title.includes('힘이'));
});

test('scrub removes effort', () => {
  const s = scrubRawTokensFromUserText('여러 구간에서 effort 관련 패턴이 반복됐어요.');
  assert.ok(!/\beffort\b/i.test(s));
});

test('unresolvedLabelKo', () => {
  assert.equal(unresolvedLabelKo('SOURCE_BALANCE'), '흉성·두성 음향 성향');
});

test('raw token detector', () => {
  assert.equal(containsRawUserFacingToken('안정적인 편'), false);
  assert.equal(containsRawUserFacingToken('STABLE'), true);
});

console.log('all result ux copy checks passed');

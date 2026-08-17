/**
 * Precision report readability presentation checks.
 * Run: npx --yes tsx miniapp/scripts/check_precision_readability.mts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  buildCompactReportDisclaimer,
  buildUncertainUserCopy,
  presentAnalysisScope,
  presentCoreFinding,
  presentSupportingList,
  presentSupportingObservation,
} from '../src/lib/precisionPresentation.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (e) {
    console.error(`FAIL - ${name}`);
    throw e;
  }
}

function readSrc(rel: string) {
  return readFileSync(join(root, rel), 'utf8');
}

test('test_progress_subtitle_does_not_say_fake_score', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(!page.includes('가짜 점수'));
  assert.ok(!page.includes('퍼센트가 아니라'));
});

test('test_progress_subtitle_explains_record_comparison', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(page.includes('이전보다 뭐가 달라졌을까요'));
  assert.ok(page.includes('이전 결과와 비교') || page.includes('최근 기록'));
});

test('test_precision_distinct_feature_has_no_decorative_01', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(!page.includes("padStart(2, '0')"));
  assert.ok(page.includes('확인된 핵심 특징'));
  assert.ok(!page.includes('가장 뚜렷한 특징'));
});

test('test_precision_distinct_feature_does_not_concat_tone', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(!page.includes('diag-tone'));
  assert.ok(!page.includes('finding.tone'));
});

test('test_precision_finding_title_is_human_readable', () => {
  const shown = presentCoreFinding({
    title: '발성 안정성',
    body: '지속음은 전반적으로 큰 흔들림 없이 이어졌어요.',
    tone: '보통',
  });
  assert.equal(shown.title, '발성 안정성');
  assert.ok(!shown.title.includes('보통'));
  assert.ok(shown.body.includes('이어졌어요'));
});

test('test_supporting_section_uses_user_facing_title', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(page.includes('참고로 확인된 변화'));
  assert.ok(!page.includes('추가로 관찰된 특징'));
});

test('test_meta_only_supporting_observation_hidden', () => {
  const p = presentSupportingObservation({
    mechanism_id: 'phonatory_efficiency',
    display_name: '발성 효율',
    observation: '주기성 관련 관측이 있으나 ‘발성 효율’로 점수화하지는 않았어요.',
  });
  assert.equal(p.visible, false);
});

test('test_useful_supporting_observation_preserved', () => {
  const list = presentSupportingList([
    {
      mechanism_id: 'phonatory_efficiency',
      observation: '주기성 관련 관측이 있으나 ‘발성 효율’로 점수화하지는 않았어요.',
    },
    {
      mechanism_id: 'release_coordination',
      observation: '끝음 구간의 에너지 변화가 관측됐어요. 끝음 조절 결론은 내리지 않았어요.',
    },
    {
      mechanism_id: 'vocal_tract_resonance_balance',
      observation: '모음에 따라 스펙트럼 분포가 달라지는 경향이 관찰됐어요.',
    },
  ]);
  assert.equal(list.length, 2);
  assert.ok(list.every((x) => x.visible));
});

test('test_release_energy_change_has_natural_korean_copy', () => {
  const p = presentSupportingObservation({
    mechanism_id: 'release_coordination',
    observation: '끝음 구간의 에너지 변화가 관측됐어요. 끝음 조절 결론은 내리지 않았어요.',
  });
  assert.equal(p.visible, true);
  assert.equal(p.title, '구절 끝의 변화');
  assert.ok(p.body.includes('소리 크기'));
  assert.ok(!p.body.includes('결론은 내리지'));
});

test('test_resonance_observation_has_natural_user_copy', () => {
  const p = presentSupportingObservation({
    mechanism_id: 'vocal_tract_resonance_balance',
    observation: '모음에 따라 스펙트럼 분포가 달라지는 경향이 관찰됐어요.',
  });
  assert.equal(p.visible, true);
  assert.equal(p.title, '모음에 따른 음색 변화');
  assert.ok(p.body.includes('음색'));
  assert.ok(!p.body.includes('스펙트럼'));
});

test('test_uncertain_section_title_is_not_additional_confirmation_needed', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(!page.includes('추가 확인이 필요한 항목'));
});

test('test_uncertain_section_title_is_confirm_not_decided_wording', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(page.includes('이번에 확정하지 않은 부분'));
});

test('test_uncertain_register_copy_explains_missing_comparison', () => {
  const c = buildUncertainUserCopy(
    'register_transition_coordination',
    '이번 녹음에서는 충분한 근거가 없어 이 항목은 판단하지 않았어요.',
  );
  assert.ok(c.body.includes('성구 연결'));
  assert.ok(c.body.includes('충분하지'));
  assert.ok(!c.body.includes('판단하지 않았'));
});

test('test_uncertain_contact_hides_raw_a_i_tokens', () => {
  const c = buildUncertainUserCopy(
    'phonation_contact_pattern',
    'a · 와 · i · 에서 방향이 달라 단정하지 않았어요.',
  );
  assert.ok(!/\ba\b/.test(c.body));
  assert.ok(!/\bi\b/.test(c.body));
});

test('test_uncertain_contact_says_vowels_differ', () => {
  const c = buildUncertainUserCopy(
    'phonation_contact_pattern',
    'a · 와 · i · 에서 방향이 달라 단정하지 않았어요.',
  );
  assert.ok(c.body.includes('모음'));
  assert.ok(c.body.includes('한 방향으로'));
});

test('test_uncertain_dynamics_copy_is_natural', () => {
  const c = buildUncertainUserCopy(
    'intensity_phonation_coordination',
    '이번 과제에서는 비교할 수 있는 구간이 충분하지 않았어요.',
  );
  assert.ok(c.body.includes('강약 변화'));
  assert.ok(c.body.includes('추가 녹음'));
});

test('test_analysis_scope_does_not_say_song_analysis_used', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(!page.includes('노래 분석 사용함'));
  const s = presentAnalysisScope({
    evidence_mode: 'PARTIAL_PRECISION',
    completed_task_count: 1,
    user_skipped_task_count: 2,
  });
  assert.ok(!s.body.includes('노래 분석 사용함'));
});

test('test_partial_scope_says_actual_completed_recordings', () => {
  const s = presentAnalysisScope({
    evidence_mode: 'PARTIAL_PRECISION',
    completed_task_count: 1,
    user_skipped_task_count: 2,
  });
  assert.equal(s.visible, true);
  assert.equal(s.title, '이번 진단에 사용한 녹음');
  assert.ok(s.body.includes('추가 발성 녹음 1개'));
});

test('test_skipped_recordings_are_explained_naturally', () => {
  const s = presentAnalysisScope({
    evidence_mode: 'PARTIAL_PRECISION',
    completed_task_count: 1,
    user_skipped_task_count: 2,
  });
  assert.ok(s.detail?.includes('건너뛰어'));
  assert.ok(s.detail?.includes('추가 녹음 2개'));
});

test('test_full_precision_scope_can_be_hidden_when_not_needed', () => {
  const s = presentAnalysisScope({
    evidence_mode: 'FULL_PRECISION',
    completed_task_count: 3,
    user_skipped_task_count: 0,
  });
  assert.equal(s.visible, false);
});

test('test_analysis_method_limit_accordion_removed', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(!page.includes('분석 방법과 한계'));
  const more = readSrc('src/components/report/MoreDetails.tsx');
  assert.ok(!more.includes('분석 방법과 한계'));
});

test('test_compact_disclaimer_still_visible', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(page.includes('precision-disclaimer'));
  const d = buildCompactReportDisclaimer();
  assert.ok(d.includes('의료'));
});

test('test_medical_disclaimer_not_removed', () => {
  const d = buildCompactReportDisclaimer('성대의 실제 구조나 질환을 진단하는 검사가 아닙니다.');
  assert.ok(/성대|질환|의료|의학/.test(d));
});

test('test_safety_warning_remains_prominent', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(page.includes('className="warn"'));
  assert.ok(page.includes('safetyNote'));
});

test('test_debug_can_still_show_raw_diagnostic_information', () => {
  const page = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(page.includes('scientific_debug'));
  assert.ok(page.includes('showDebug'));
});

console.log('\nAll precision readability checks passed.');

/**
 * Goal surface simplification — Home/Result/Progress goal-free UI.
 * Run: npx --yes tsx miniapp/scripts/check_goal_surface.mts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildLocalProgressInsight } from '../src/lib/progressPresentation.ts';

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

function auditNoGoalMgmt(src: string, label: string) {
  assert.ok(!src.includes('이번 목표'), `${label}: 이번 목표`);
  assert.ok(!src.includes('목표 정하기'), `${label}: 목표 정하기`);
  assert.ok(!src.includes('목표 바꾸기'), `${label}: 목표 바꾸기`);
  assert.ok(!src.includes('목표 정하러 가기'), `${label}: 목표 정하러 가기`);
  assert.ok(!src.includes('목표 방향'), `${label}: 목표 방향`);
  assert.ok(!/달성률/.test(src), `${label}: 달성률`);
}

test('test_home_does_not_render_current_goal', () => {
  const home = readSrc('src/pages/Home.tsx');
  assert.ok(!home.includes('GoalProgressCard'));
  assert.ok(!home.includes('home-goal-card'));
  assert.ok(!home.includes('getVocalGoalProgress'));
  auditNoGoalMgmt(home, 'Home');
});

test('test_home_does_not_render_goal_progress_count', () => {
  const home = readSrc('src/pages/Home.tsx');
  assert.ok(!home.includes('goal_aligned'));
  assert.ok(!home.includes('GoalEvidenceDots'));
});

test('test_home_still_links_to_progress', () => {
  const home = readSrc('src/pages/Home.tsx');
  assert.ok(home.includes('home-progress-link') || home.includes('to="/progress"'));
  assert.ok(home.includes('내 변화 보기'));
});

test('test_free_result_does_not_render_goal_card', () => {
  const result = readSrc('src/pages/Result.tsx');
  const today = readSrc('src/components/progress/TodayPhonationSummary.tsx');
  assert.ok(!result.includes('GoalProgressCard'));
  assert.ok(!today.includes('GoalProgressCard'));
  assert.ok(!today.includes('goalProgress'));
  auditNoGoalMgmt(result, 'Result');
  auditNoGoalMgmt(today, 'TodayPhonationSummary');
});

test('test_free_result_does_not_render_goal_change', () => {
  const result = readSrc('src/pages/Result.tsx');
  assert.ok(!result.includes('GoalSelectorSheet'));
  assert.ok(!result.includes('목표 바꾸기'));
  assert.ok(!result.includes('sheetMode'));
});

test('test_free_result_progress_cards_can_still_be_goal_aware_internally', () => {
  const result = readSrc('src/pages/Result.tsx');
  assert.ok(result.includes('getLocalActiveGoal'));
  assert.ok(result.includes('goal:') || result.includes('goal_focus'));
  assert.ok(result.includes('buildLocalProgressInsight') || result.includes('postVocalProgressInsight'));
});

test('test_progress_has_no_goal_empty_state', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(!page.includes('progress-no-goal'));
  assert.ok(!page.includes('아직 연습 목표가 없어요'));
  assert.ok(!page.includes('buildNoGoalCta'));
});

test('test_progress_has_no_current_goal_section', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(!page.includes('현재 목표'));
  assert.ok(!page.includes('GoalProgressCard'));
  assert.ok(!page.includes('progress-goal-section'));
});

test('test_progress_has_no_previous_goal_section', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(!page.includes('이전 목표'));
  assert.ok(!page.includes('listLocalGoalHistory'));
});

test('test_progress_has_no_goal_setting_cta', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(!page.includes('목표 정하러 가기'));
  assert.ok(!page.includes('목표 정하기'));
  assert.ok(!page.includes('progress-no-goal-cta'));
});

test('test_progress_has_no_detail_purchase_cta_for_goal', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(!page.includes('상세 리포트 보기'));
  assert.ok(!page.includes('focusOffer'));
});

test('test_progress_generic_changes_work_without_goal', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(page.includes('progress-generic-changes'));
  assert.ok(page.includes('좋아진 부분'));
  assert.ok(page.includes('달라진 부분'));
  assert.ok(page.includes('유지하고 있는 부분'));
});

test('test_progress_improved_classification_can_use_hidden_goal_context', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(page.includes('getLocalActiveGoal'));
  assert.ok(page.includes('goal: activeFocus') || page.includes('goal: active'));
  const out = buildLocalProgressInsight(
    { register_connection: 'CONNECTED' },
    [
      { canonical: { register_connection: 'PARTIAL' } },
      { canonical: { register_connection: 'PARTIAL' } },
      { canonical: { register_connection: 'DISRUPTED' } },
    ],
    { goal: 'REGISTER_CONNECTION', recentN: 5 },
  );
  assert.ok(out.improved.some((c) => c.axis === 'register_connection'));
});

test('test_detail_is_only_user_goal_setting_surface', () => {
  const detail = readSrc('src/pages/SongDetailReport.tsx');
  assert.ok(detail.includes('GoalSelectorSheet'));
  assert.ok(detail.includes('목표 정하기') || detail.includes('GoalEmptyCta'));
  assert.ok(detail.includes('목표 바꾸기'));
  assert.ok(detail.includes('내 연습 목표'));
});

test('test_detail_shows_active_goal_after_hydration', () => {
  const detail = readSrc('src/pages/SongDetailReport.tsx');
  assert.ok(detail.includes('GoalLoadState') || detail.includes('goalState'));
  assert.ok(detail.includes('detail-goal-loading'));
  assert.ok(detail.includes('resolveActiveGoalLoadState'));
});

test('test_goal_loading_does_not_render_no_goal_state', () => {
  const hyd = readSrc('src/lib/goalHydration.ts');
  assert.ok(hyd.includes("'loading'"));
  assert.ok(hyd.includes("'none'"));
  assert.ok(hyd.includes("'ready'"));
  const detail = readSrc('src/pages/SongDetailReport.tsx');
  assert.ok(detail.includes("status === 'loading'"));
  assert.ok(detail.includes("status === 'ready'"));
});

test('test_goal_loading_does_not_flash_set_goal_cta', () => {
  const detail = readSrc('src/pages/SongDetailReport.tsx');
  // loading branch must not fall through to GoalEmptyCta without status check
  assert.ok(detail.includes("goalState.status === 'loading'"));
  assert.ok(detail.includes("goalState.status === 'ready'"));
  assert.ok(detail.includes('GoalEmptyCta'));
  // Explicit ternary: loading → ready → else empty
  const loadingBeforeReady =
    detail.indexOf("status === 'loading'") < detail.indexOf("status === 'ready'");
  assert.ok(loadingBeforeReady);
});

test('test_precision_coaching_goal_not_confused_with_user_goal', () => {
  const prem = readSrc('src/pages/PremiumReport.tsx');
  assert.ok(prem.includes('먼저 연습할 부분'));
  assert.ok(!prem.includes('>이번 목표<'));
  assert.ok(!prem.includes('section-title">이번 목표'));
});

test('test_progress_sheet_has_no_goal_mode_in_default_flow', () => {
  const sheet = readSrc('src/components/progress/ProgressInsightSheet.tsx');
  assert.ok(!sheet.includes("mode === 'goal'"));
  assert.ok(!sheet.includes('goal-progress-sheet'));
  assert.ok(!sheet.includes('목표 방향 결과'));
});

test('test_progress_navigation_back_home_unchanged', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(page.includes('SubPageHeader'));
  assert.ok(page.includes('title="내 변화"'));
  assert.ok(page.includes('resolveProgressBackTarget'));
});

console.log('\nAll goal surface checks passed.');

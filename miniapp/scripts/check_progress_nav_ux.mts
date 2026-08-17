/**
 * Progress navigation UX checks (goal-free progress page).
 * Run: npx --yes tsx miniapp/scripts/check_progress_nav_ux.mts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  isSafeInternalReturnTo,
  progressLinkState,
  resolveProgressBackTarget,
  sanitizeReturnTo,
} from '../src/lib/progressNavigation.ts';

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

test('test_progress_rejects_external_return_to', () => {
  assert.equal(isSafeInternalReturnTo('https://evil.com'), false);
  assert.equal(isSafeInternalReturnTo('//evil.com'), false);
  assert.equal(isSafeInternalReturnTo('javascript:alert(1)'), false);
  assert.equal(sanitizeReturnTo('https://x.com', '/'), '/');
});

test('test_progress_accepts_internal_return_to', () => {
  assert.equal(isSafeInternalReturnTo('/'), true);
  assert.equal(isSafeInternalReturnTo('/result/abc'), true);
  assert.equal(isSafeInternalReturnTo('/history'), true);
});

test('test_progress_back_returns_to_result_when_opened_from_result', () => {
  const r = resolveProgressBackTarget({ returnTo: '/result/xyz' });
  assert.deepEqual(r, { mode: 'path', path: '/result/xyz' });
});

test('test_progress_back_returns_home_when_opened_from_home', () => {
  const r = resolveProgressBackTarget({ returnTo: '/' });
  assert.deepEqual(r, { mode: 'path', path: '/' });
});

test('test_progress_direct_entry_back_falls_back_home', () => {
  const r = resolveProgressBackTarget({}, { navigationType: 'POP' });
  assert.deepEqual(r, { mode: 'home' });
});

test('test_progress_push_without_return_uses_history', () => {
  const r = resolveProgressBackTarget({}, { navigationType: 'PUSH' });
  assert.deepEqual(r, { mode: 'history' });
});

test('test_result_progress_link_sets_return_to_result', () => {
  assert.equal(progressLinkState('/result/abc123').returnTo, '/result/abc123');
});

test('test_home_progress_link_sets_return_to_home', () => {
  assert.equal(progressLinkState('/').returnTo, '/');
});

test('test_progress_header_has_back_left_and_home_right', () => {
  const header = readSrc('src/components/ui/SubPageHeader.tsx');
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(header.includes('aria-label="이전 화면으로 돌아가기"'));
  assert.ok(header.includes('aria-label="홈으로 이동"'));
  assert.ok(page.includes('title="내 변화"'));
  assert.ok(page.includes('SubPageHeader'));
});

test('test_progress_has_no_goal_management_ui', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(!page.includes('GoalSelectorSheet'));
  assert.ok(!page.includes('GoalProgressCard'));
  assert.ok(!page.includes('목표 정하기'));
  assert.ok(!page.includes('목표 바꾸기'));
  assert.ok(!page.includes('목표 정하러 가기'));
  assert.ok(!page.includes('현재 목표'));
});

test('test_detail_still_allows_goal_setting', () => {
  const detail = readSrc('src/pages/SongDetailReport.tsx');
  assert.ok(detail.includes('GoalSelectorSheet'));
  assert.ok(detail.includes('goal-setting'));
  assert.ok(detail.includes('GoalEmptyCta') || detail.includes('목표 정하기'));
});

test('test_detail_still_allows_goal_change', () => {
  const detail = readSrc('src/pages/SongDetailReport.tsx');
  assert.ok(detail.includes('목표 바꾸기'));
});

test('test_progress_shows_generic_changes', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(page.includes('progress-generic-changes'));
  assert.ok(page.includes('좋아진 부분') || page.includes('달라진 부분'));
});

test('test_free_result_still_has_no_goal_selector', () => {
  const result = readSrc('src/pages/Result.tsx');
  assert.ok(!result.includes('GoalSelectorSheet'));
  assert.ok(!result.includes('목표 정하기'));
});

test('test_result_and_home_carry_return_context', () => {
  const today = readSrc('src/components/progress/TodayPhonationSummary.tsx');
  assert.ok(today.includes('progressLinkState') || today.includes('returnTo'));
  const home = readSrc('src/pages/Home.tsx');
  assert.ok(home.includes('progressLinkState') || home.includes('returnTo'));
});

test('test_progress_insight_sheet_still_opens', () => {
  const page = readSrc('src/pages/ProgressInsight.tsx');
  assert.ok(page.includes('ProgressInsightSheet'));
  assert.ok(page.includes('setSheetCard'));
});

console.log('\nAll progress nav UX checks passed.');

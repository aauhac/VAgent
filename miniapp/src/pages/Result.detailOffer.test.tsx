/**
 * The locked 상세 리포트 offer must actually reach the DOM on a free result.
 *
 * Source greps kept passing while the real device showed nothing, so these render the
 * page and assert on the rendered output. The card is decided by `!song_detail_unlocked`
 * alone; the ad option and the paid option are decided separately, so one failing
 * subsystem may remove an option but never the offer itself.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const ANALYSIS_ID = 'a'.repeat(32);

const getAnalysis = vi.fn();
const getProducts = vi.fn();
const getAnalysisAccess = vi.fn();
const patchHistory = vi.fn();
const useIapProductPrices = vi.fn();
const useRewardedDetailUnlock = vi.fn();

vi.mock('../api/client', () => ({
  getAnalysis: (...a: unknown[]) => getAnalysis(...a),
  getProducts: (...a: unknown[]) => getProducts(...a),
  getAnalysisAccess: (...a: unknown[]) => getAnalysisAccess(...a),
  patchHistory: (...a: unknown[]) => patchHistory(...a),
  postVocalProgressInsight: vi.fn(async () => null),
  postVocalSnapshot: vi.fn(async () => null),
  saveSongDetailUnlock: vi.fn(),
}));
vi.mock('../lib/useIapProductPrices', () => ({
  useIapProductPrices: (...a: unknown[]) => useIapProductPrices(...a),
}));
vi.mock('../lib/useRewardedDetailUnlock', () => ({
  useRewardedDetailUnlock: (...a: unknown[]) => useRewardedDetailUnlock(...a),
}));
vi.mock('../lib/tossIap', () => ({ buyProduct: vi.fn(async () => ({ ok: false, state: 'CANCELLED' })) }));

import Result from './Result';

function freeResult(overrides: Record<string, unknown> = {}) {
  return {
    result: {
      analysis_id: ANALYSIS_ID,
      score: { available: true, areas: [] },
      access: { song_detail_unlocked: false, diagnostic_unlocked: false, diagnostic_session_id: null },
      vocal_type_teaser: { available: true, display_name: '균형형' },
      disclaimer: '참고용 정보예요.',
      ...overrides,
    },
  };
}

function prices(state: 'ready' | 'loading' | 'retryable', paymentsEnabled = true) {
  const song =
    state === 'ready'
      ? { label: '990원', canPurchase: true, retryable: false }
      : state === 'retryable'
        ? { label: '가격을 불러오지 못했어요.', canPurchase: false, retryable: true }
        : { label: '가격 확인 중…', canPurchase: false, retryable: false };
  return {
    prices: { song_detail: song, diagnostic_full: { label: '1,980원', canPurchase: true } },
    reload: vi.fn(),
    paymentsEnabled,
  };
}

function rewarded(loadState: string, opts: { configured?: boolean; canOffer?: boolean } = {}) {
  const configured = opts.configured ?? true;
  const canOffer = opts.canOffer ?? (configured && loadState !== 'unavailable');
  return {
    status: { remaining_today: 3, daily_limit: 3, can_use_rewarded_ad: true, already_unlocked: false },
    loadState,
    busy: false,
    error: null,
    configured,
    canOffer,
    remainingToday: 3,
    dailyLimit: 3,
    refreshStatus: vi.fn(),
    retryLoad: vi.fn(),
    watchAndUnlock: vi.fn(),
  };
}

async function renderResult() {
  render(
    <MemoryRouter initialEntries={[`/result/${ANALYSIS_ID}`]}>
      <Routes>
        <Route path="/result/:id" element={<Result />} />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() => expect(screen.getByText('상세 리포트')).toBeInTheDocument());
}

function offerCard() {
  return screen.getByTestId('offer-song-detail');
}

beforeEach(() => {
  getAnalysis.mockResolvedValue(freeResult());
  getProducts.mockResolvedValue({ payments_enabled: true, offers: { diagnostic: 'diagnostic_full' } });
  getAnalysisAccess.mockResolvedValue({ song_detail_unlocked: false });
  useIapProductPrices.mockReturnValue(prices('ready'));
  useRewardedDetailUnlock.mockReturnValue(rewarded('ready'));
});

describe('free result — locked 상세 리포트 offer', () => {
  it('A. renders the card and both options when ad and purchase are ready', async () => {
    await renderResult();
    const card = offerCard();
    expect(within(card).getByRole('button', { name: '광고 보고 무료로 열기' })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: '990원에 상세 리포트 열기' })).toBeInTheDocument();
    expect(within(card).getByText('오늘 무료 열람 3회 남음')).toBeInTheDocument();
  });

  it('B. ad loading keeps the purchase option', async () => {
    useRewardedDetailUnlock.mockReturnValue(rewarded('loading'));
    await renderResult();
    const card = offerCard();
    expect(within(card).getByRole('button', { name: '광고 준비 중…' })).toBeDisabled();
    expect(within(card).getByRole('button', { name: '990원에 상세 리포트 열기' })).toBeEnabled();
  });

  it('C. ad error offers a retry and keeps the purchase option', async () => {
    await (async () => {
      useRewardedDetailUnlock.mockReturnValue(rewarded('error'));
      await renderResult();
    })();
    const card = offerCard();
    expect(within(card).getByRole('button', { name: '광고 다시 시도' })).toBeEnabled();
    expect(within(card).getByRole('button', { name: '990원에 상세 리포트 열기' })).toBeInTheDocument();
  });

  it('D. ad unavailable explains itself and keeps the purchase option', async () => {
    useRewardedDetailUnlock.mockReturnValue(rewarded('unavailable', { canOffer: false }));
    await renderResult();
    const card = offerCard();
    expect(within(card).getByText('지금은 광고 무료 열람을 사용할 수 없어요.')).toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: '광고 보고 무료로 열기' })).toBeNull();
    expect(within(card).getByRole('button', { name: '990원에 상세 리포트 열기' })).toBeInTheDocument();
  });

  it('E. price still loading keeps the ad option and shows a price placeholder', async () => {
    useIapProductPrices.mockReturnValue(prices('loading'));
    await renderResult();
    const card = offerCard();
    expect(within(card).getByRole('button', { name: '광고 보고 무료로 열기' })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: '가격 확인 중…' })).toBeDisabled();
  });

  it('E2. an unusable price offers a retry rather than hiding the offer', async () => {
    useIapProductPrices.mockReturnValue(prices('retryable'));
    await renderResult();
    expect(within(offerCard()).getByRole('button', { name: '가격 다시 확인하기' })).toBeInTheDocument();
  });

  it('F. the card survives when BOTH the ad and commerce are unavailable', async () => {
    useRewardedDetailUnlock.mockReturnValue(rewarded('unavailable', { canOffer: false }));
    useIapProductPrices.mockReturnValue({ ...prices('loading', false), paymentsEnabled: false });
    await renderResult();
    expect(offerCard()).toBeInTheDocument();
    expect(screen.getByText('상세 리포트')).toBeInTheDocument();
  });

  it('G. an unlocked analysis shows the open link instead of the offer', async () => {
    getAnalysis.mockResolvedValue(
      freeResult({ access: { song_detail_unlocked: true, diagnostic_unlocked: false, diagnostic_session_id: null } }),
    );
    await renderResult();
    expect(screen.getByRole('link', { name: '상세 리포트 보기' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '광고 보고 무료로 열기' })).toBeNull();
    expect(screen.queryByRole('button', { name: '990원에 상세 리포트 열기' })).toBeNull();
  });

  it('a catalog outage must not turn a healthy analysis into the expired screen', async () => {
    getProducts.mockRejectedValue(new Error('catalog down'));
    useIapProductPrices.mockReturnValue({ ...prices('loading', false), paymentsEnabled: false });
    await renderResult();
    expect(screen.queryByText('분석 기록이 만료됐어요.')).toBeNull();
    expect(offerCard()).toBeInTheDocument();
    // The ad is independent of commerce, so it is still offered.
    expect(within(offerCard()).getByRole('button', { name: '광고 보고 무료로 열기' })).toBeInTheDocument();
  });
});

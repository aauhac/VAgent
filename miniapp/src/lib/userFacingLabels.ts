/**
 * Canonical user-facing Korean labels for vocal axes/states.
 * Default UI must never show raw English enums (STABLE, FIRM, effort, …).
 */

export const AXIS_LABEL_KO: Record<string, string> = {
  effort: '힘 사용',
  contact: '접촉감',
  breathiness: '숨 섞임',
  register_connection: '성구 연결',
  stability: '발성 안정성',
  brightness: '밝기',
  source_balance: '흉성·두성 음향 성향',
  presence: '중역 존재감',
  timbre: '음색',
};

/** Short chip labels for sequence rows (Korean only). */
export const STATE_CHIP_KO: Record<string, string> = {
  CONNECTED: '연결',
  PARTIAL: '일부',
  DISRUPTED: '끊김',
  UNRESOLVED: '확인 부족',
  STABLE: '안정',
  UNSTABLE: '흔들림',
  FIRM: '단단함',
  MID: '중간',
  LIGHT: '가벼움',
  AMBIGUOUS: '애매',
  LOW: '낮음',
  MODERATE: '보통',
  HIGH: '높음',
  UNKNOWN: '확인 부족',
  UNAVAILABLE: '확인 부족',
  CHEST_LEANING: '흉성 쪽',
  CHEST_DOMINANT: '흉성 강함',
  HEAD_LEANING: '두성 쪽',
  HEAD_DOMINANT: '두성 강함',
  BALANCED: '균형',
  BALANCED_ACOUSTIC: '균형',
  CONFLICTED: '구간마다 다름',
};

export const STATE_LABEL_KO: Record<string, string> = {
  CONNECTED: '자연스럽게 연결되는 편',
  PARTIAL: '일부 구간만 연결되는 편',
  DISRUPTED: '연결이 끊기는 구간이 있는 편',
  UNRESOLVED: '이번에는 연결 상태를 판단하기 어려워요',
  STABLE: '안정적인 편',
  UNSTABLE: '흔들림이 있는 편',
  FIRM: '단단한 편',
  MID: '중간 편',
  LIGHT: '가벼운 편',
  AMBIGUOUS: '구간에 따라 다른 편',
  LOW: '낮은 편',
  MODERATE: '중간 정도',
  HIGH: '높은 편',
  UNKNOWN: '이번에는 확인이 어려워요',
  UNAVAILABLE: '이번엔 확인이 어려워요',
  CHEST_LEANING: '흉성 쪽',
  CHEST_DOMINANT: '흉성 쪽 성향이 강한 편',
  HEAD_LEANING: '두성 쪽',
  HEAD_DOMINANT: '두성 쪽 성향이 강한 편',
  BALANCED: '균형적인 편',
  BALANCED_ACOUSTIC: '균형적인 편',
  CONFLICTED: '구간마다 다른 편',
};

const RAW_TOKEN_RE =
  /\b(effort|STABLE|UNSTABLE|FIRM|LIGHT|MID|LOW|MODERATE|HIGH|CONNECTED|PARTIAL|DISRUPTED|UNRESOLVED|CHEST_LEANING|CHEST_DOMINANT|HEAD_LEANING|HEAD_DOMINANT|BALANCED_ACOUSTIC|BALANCED|CONFLICTED|UNKNOWN|UNAVAILABLE|REGISTER_CONNECTION|SOURCE_BALANCE|BREATHINESS|CONTACT)\b/gi;

export function axisLabelKo(axis: string): string {
  return AXIS_LABEL_KO[axis] || axis;
}

export function stateLabelKo(raw: string | null | undefined): string {
  if (raw == null || raw === '') return '이번에는 확인이 어려워요';
  const key = String(raw).toUpperCase().trim();
  return STATE_LABEL_KO[key] || String(raw);
}

export function stateChipKo(raw: string | null | undefined): string {
  if (raw == null || raw === '') return '확인 부족';
  const key = String(raw).toUpperCase().trim();
  return STATE_CHIP_KO[key] || stateLabelKo(key).replace(/ 편$/, '').slice(0, 6);
}

/** Window wording from actual history length — never invent "최근 5회" for n=1. */
export function recentWindowLabel(actualCount: number, requestedN = 5): string {
  const n = Math.max(0, actualCount);
  if (n <= 0) return '이전 기록';
  if (n === 1) return '이전 기록';
  if (n < requestedN) return `최근 ${n}회`;
  return `최근 ${requestedN}회`;
}

export function howMuchStableSummary(actualCount: number, hitCount: number, requestedN = 5): string {
  const n = Math.max(0, actualCount);
  if (n <= 0) return '비교할 이전 기록이 아직 없어요.';
  if (n === 1) {
    return hitCount > 0
      ? '이전 기록에서도 안정적인 편이었어요.'
      : '이전 기록과 비교해 보면 아직 안정적으로 보이진 않았어요.';
  }
  const window = Math.min(n, requestedN);
  return `${recentWindowLabel(window, requestedN)} 중 안정적인 결과 ${hitCount}회`;
}

export function buildAxisChangeCopy(
  axis: string,
  previousRaw: string,
  currentRaw: string,
): string {
  const prev = stateLabelKo(previousRaw);
  const cur = stateLabelKo(currentRaw);
  switch (axis) {
    case 'effort':
      return effortChangeCopy(previousRaw, currentRaw);
    case 'contact':
      return `접촉감이 ${prev.replace(/ 편$/, '')} 쪽에서 ${cur}으로 바뀌었어요.`;
    case 'breathiness':
      return `숨 섞임이 ${prev}에서 ${cur}으로 나타났어요.`;
    case 'register_connection':
      return `이전보다 성구가 ${cur}으로 나타났어요.`;
    case 'stability':
      return `발성 안정성이 ${prev}에서 ${cur}으로 나타났어요.`;
    case 'brightness':
      return `이전보다 ${cur.replace(/ 편$/, '')} 쪽으로 이동했어요.`;
    case 'source_balance':
      return `이번에는 이전보다 ${cur} 음향 성향이 더 나타났어요.`;
    case 'presence':
      return `중역 존재감이 ${prev}에서 ${cur}으로 나타났어요.`;
    default:
      return `이전에는 ${prev}이었고, 이번에는 ${cur}으로 나타났어요.`;
  }
}

function effortChangeCopy(previousRaw: string, currentRaw: string): string {
  const order = { LOW: 0, MODERATE: 1, HIGH: 2 } as Record<string, number>;
  const a = order[String(previousRaw).toUpperCase()];
  const b = order[String(currentRaw).toUpperCase()];
  if (a != null && b != null && b < a) {
    return '이전 기록보다 힘을 덜 쓰는 쪽으로 나타났어요.';
  }
  if (a != null && b != null && b > a) {
    return '이전 기록보다 힘이 더 들어가는 쪽으로 나타났어요.';
  }
  return `힘 사용이 ${stateLabelKo(previousRaw)}에서 ${stateLabelKo(currentRaw)}으로 나타났어요.`;
}

export function buildAxisMaintainedCopy(axis: string, currentRaw: string): string {
  const cur = stateLabelKo(currentRaw);
  if (axis === 'effort') return '최근 기록과 비슷하게 힘을 쓰는 편이에요.';
  if (axis === 'stability') return '최근 기록과 비슷하게 안정적인 편이에요.';
  if (axis === 'register_connection') return '최근 기록과 비슷한 성구 연결 상태예요.';
  if (axis === 'contact') return `최근 기록과 비슷하게 ${cur}이에요.`;
  return `최근 기록과 비슷하게 ${cur}이에요.`;
}

/** Diagnostic unresolved labels → Korean. */
export function unresolvedLabelKo(raw: string): string {
  const map: Record<string, string> = {
    REGISTER_CONNECTION: '성구 연결',
    BREATHINESS: '숨 섞임',
    CONTACT: '접촉감',
    EFFORT: '힘 사용',
    STABILITY: '발성 안정성',
    BRIGHTNESS: '밝기',
    PRESENCE: '중역 존재감',
    SOURCE_BALANCE: '흉성·두성 음향 성향',
    HIGH_NOTE_ACCESS: '고음 접근',
    PITCH_STABILITY: '음정 안정성',
  };
  const key = String(raw || '').toUpperCase();
  return map[key] || AXIS_LABEL_KO[key.toLowerCase()] || String(raw);
}

export function scrubRawTokensFromUserText(text: string): string {
  if (!text) return text;
  return String(text)
    .replace(/\beffort\b/gi, '힘 사용')
    .replace(/\bSOURCE[_\s-]?BALANCE\b/gi, '흉성·두성 음향 성향')
    .replace(/\bREGISTER[_\s-]?CONNECTION\b/gi, '성구 연결')
    .replace(RAW_TOKEN_RE, (m) => {
      const up = m.toUpperCase();
      if (STATE_LABEL_KO[up]) return STATE_CHIP_KO[up] || STATE_LABEL_KO[up];
      if (up === 'EFFORT') return '힘 사용';
      return '';
    })
    .replace(/\s{2,}/g, ' ')
    .trim();
}

export function containsRawUserFacingToken(text: string): boolean {
  return RAW_TOKEN_RE.test(String(text || ''));
}

export function containsIgaPlaceholder(text: string): boolean {
  return String(text || '').includes('이(가)');
}

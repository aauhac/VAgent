/**
 * Precision report presentation only — filter/rename/copy for user UI.
 * Does not change reliable/uncertain classification or backend payloads.
 */

import { sanitizeDisclaimer, scrubUserText, translateMechanismTitle } from './reportPresentation';

export type PresentedObservation = {
  visible: boolean;
  title: string;
  body: string;
  mechanismId?: string;
};

const META_ENGINE_RE =
  /점수화하지|결론은 내리지|판단은 보류|판단하지 않았|별도 점수로|보조 관측만|메커니즘 진단이 아니라/;

const SUPPORTING_TITLE: Record<string, string> = {
  release_coordination: '구절 끝의 변화',
  vocal_tract_resonance_balance: '모음에 따른 음색 변화',
  phonatory_efficiency: '발성 효율',
};

const SUPPORTING_BODY: Record<string, string> = {
  release_coordination:
    '일부 구절 끝에서 소리 크기가 달라지는 구간이 있었어요.',
  vocal_tract_resonance_balance:
    '모음이 바뀔 때 음색 특성이 달라지는 경향이 있었어요.',
};

/** Split Korean sentences without inventing claims. */
function splitSentences(text: string): string[] {
  const t = (text || '').trim();
  if (!t) return [];
  return t
    .split(/(?<=[.。!?]|요\.|요)\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function stripMetaSentences(text: string): string {
  return splitSentences(text)
    .filter((s) => !META_ENGINE_RE.test(s))
    .join(' ')
    .trim();
}

function isMetaOnlyBody(text: string): boolean {
  const raw = (text || '').trim();
  if (!raw) return true;
  const kept = stripMetaSentences(raw);
  if (!kept) return true;
  // Entire message is engine meta (e.g. efficiency score note)
  if (META_ENGINE_RE.test(raw) && kept.length < 12) return true;
  if (/주기성 관련 관측/.test(raw) && /점수화/.test(raw)) return true;
  return false;
}

function hideRawVowels(text: string): string {
  return text
    .replace(/\ba\s*[·・/,]\s*와\s*[·・/,]?\s*i\b/gi, '모음')
    .replace(/\b([aiu])\s*[·・/]\s*([aiu])(?:\s*[·・/]\s*([aiu]))?\b/gi, '모음')
    .replace(/\b(a|i|u)\b(?=\s*에서|\s*모음|\s*·)/gi, (m) =>
      m.toLowerCase() === 'a' ? '아' : m.toLowerCase() === 'i' ? '이' : '우',
    );
}

/**
 * Map supporting observation for default UI.
 * Backend item unchanged — presentation filter only.
 */
export function presentSupportingObservation(item: any): PresentedObservation {
  const mid = String(item?.mechanism_id || '');
  const rawBody = scrubUserText(
    String(item?.observation || item?.summary || item?.what_was_observed || ''),
  );
  const mappedBody = SUPPORTING_BODY[mid];
  let body = mappedBody || stripMetaSentences(rawBody) || rawBody;

  // Prefer mapped natural copy when raw is known engine phrasing
  if (mid === 'release_coordination' && /에너지 변화|끝음/.test(rawBody)) {
    body = SUPPORTING_BODY.release_coordination;
  }
  if (mid === 'vocal_tract_resonance_balance' && /스펙트럼|모음/.test(rawBody)) {
    body = SUPPORTING_BODY.vocal_tract_resonance_balance;
  }

  body = scrubUserText(body);

  if (isMetaOnlyBody(rawBody) && !mappedBody) {
    return { visible: false, title: '', body: '', mechanismId: mid };
  }
  if (mid === 'phonatory_efficiency' && (/점수화|주기성/.test(rawBody) || isMetaOnlyBody(rawBody))) {
    return { visible: false, title: '', body: '', mechanismId: mid };
  }
  if (!body || isMetaOnlyBody(body)) {
    return { visible: false, title: '', body: '', mechanismId: mid };
  }

  const title =
    SUPPORTING_TITLE[mid]
    || translateMechanismTitle(mid, item?.display_name);

  return {
    visible: true,
    title,
    body,
    mechanismId: mid,
  };
}

/** Max useful supporting rows in default UI. */
export function presentSupportingList(items: any[] | undefined, max = 3): PresentedObservation[] {
  const out: PresentedObservation[] = [];
  for (const item of items || []) {
    const p = presentSupportingObservation(item);
    if (!p.visible) continue;
    out.push(p);
    if (out.length >= max) break;
  }
  return out;
}

export function buildUncertainUserCopy(
  mechanismId?: string,
  rawSummary?: string,
  _evidence?: unknown,
): { title: string; body: string } {
  const mid = mechanismId || '';
  const title = translateMechanismTitle(mid, undefined);
  const raw = hideRawVowels(scrubUserText(rawSummary || ''));

  if (mid === 'register_transition_coordination') {
    if (/성구가 바뀌|전환.*구간|연결.*비교/.test(raw)) {
      return {
        title,
        body: '이번에는 성구가 바뀌는 구간을 충분히 비교하기 어려워 한 방향으로 정리하지 않았어요.',
      };
    }
    return {
      title,
      body: '이번에는 성구 연결을 비교할 수 있는 구간이 충분하지 않았어요.',
    };
  }

  if (mid === 'phonation_contact_pattern') {
    if (/방향|다르|모음|a\b|i\b|아|이/.test(rawSummary || '') || /모음/.test(raw)) {
      return {
        title,
        body: '모음에 따라 접촉감 관련 결과가 다르게 나타나 이번에는 한 방향으로 정리하지 않았어요.',
      };
    }
    return {
      title,
      body: '이번에는 접촉감을 한 방향으로 정리하기에 비교 정보가 충분하지 않았어요.',
    };
  }

  if (mid === 'intensity_phonation_coordination') {
    return {
      title,
      body: '이번 추가 녹음에서는 강약 변화를 비교할 수 있는 구간이 충분하지 않았어요.',
    };
  }

  // Generic: soften engine "판단하지 않았어요" without inventing reasons
  let body = raw
    .replace(/이 항목은 판단하지 않았어요\.?/g, '한 방향으로 정리하지 않았어요.')
    .replace(/충분한 근거가 없어\s*/g, '')
    .replace(/판단 어려움/g, '');
  body = hideRawVowels(body).trim();
  if (!body || /판단하지/.test(body)) {
    body = '이번에는 비교할 수 있는 정보가 충분하지 않아 한 방향으로 정리하지 않았어요.';
  }
  return { title, body };
}

export type AnalysisScopePresentation = {
  visible: boolean;
  title: string;
  body: string;
  detail?: string;
};

/**
 * Show analysis-scope accordion only when partial / concern / skips matter.
 */
export function presentAnalysisScope(report: any): AnalysisScopePresentation {
  const mode = String(report?.evidence_mode || '');
  const skipped = Number(report?.user_skipped_task_count || 0);
  const completed = report?.completed_task_count;
  const title = '이번 진단에 사용한 녹음';

  if (mode === 'CONCERN_ONLY') {
    return {
      visible: true,
      title,
      body: '이번 진단은 추가 발성 녹음 없이 현재 노래와 선택한 고민을 중심으로 분석했어요.',
    };
  }

  const partial = mode === 'PARTIAL_PRECISION' || skipped > 0;
  if (!partial) {
    return { visible: false, title, body: '' };
  }

  const nDone = completed != null ? Number(completed) : null;
  const body =
    nDone != null && nDone > 0
      ? `노래 1개와 추가 발성 녹음 ${nDone}개를 함께 분석했어요.`
      : '노래와 완료한 추가 발성 녹음을 함께 분석했어요.';
  const detail =
    skipped > 0
      ? `추가 녹음 ${skipped}개는 건너뛰어 확인 가능한 범위 안에서 결과를 정리했어요.`
      : undefined;

  return { visible: true, title, body, detail };
}

export function buildCompactReportDisclaimer(raw?: string): string {
  const cleaned = sanitizeDisclaimer(raw);
  // Prefer short medical-boundary footer when base is the long default
  if (
    !raw
    || /의학적 검사|의료 검사|성대 구조/.test(cleaned)
  ) {
    // Keep any extra safety clauses from backend if present beyond the medical line
    const sentences = splitSentences(cleaned);
    const medical = sentences.filter(
      (s) => /성대|질환|의료|의학|진단하는 검사/.test(s),
    );
    const extra = sentences.filter(
      (s) => !/성대|질환|의료|의학|진단하는 검사|음향적 특성|발성 패턴을 분석/.test(s),
    );
    const core =
      '이 결과는 녹음에서 나타난 발성 경향을 분석한 것으로, 성대 구조나 질환을 확인하는 의료 검사는 아니에요.';
    if (extra.length) {
      return `${core} ${extra.join(' ')}`.trim();
    }
    if (medical.length && medical.join(' ').length > 40) {
      return scrubUserText(medical.join(' ')) || core;
    }
    return core;
  }
  return cleaned;
}

/** Core finding card: title + optional body; never concat tone. */
export function presentCoreFinding(finding: {
  title: string;
  body?: string;
  tone?: string;
}): { title: string; body: string } {
  return {
    title: scrubUserText(finding.title || '').replace(/\s+/g, ' ').trim(),
    body: scrubUserText(finding.body || '').trim(),
  };
}

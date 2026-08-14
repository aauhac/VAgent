import { useState } from 'react';
import { scrubUserText } from '../../lib/reportPresentation';

type Step = {
  level?: number;
  id?: string;
  title?: string;
  instruction?: string;
  repetitions?: string;
  success_cues?: string[];
  failure_cues?: string[];
  next_preview?: string;
  regress_preview?: string;
};

type Protocol = {
  version?: string;
  primary_focus?: string;
  protocol_id?: string;
  reason?: string;
  entry_level?: number;
  entry_step?: Step;
  steps?: Step[];
  song_transfer?: {
    instruction?: string;
    success_cues?: string[];
    fallback_step?: number;
  };
  if_better?: string;
  if_worse?: string;
  target_overlay?: {
    label?: string;
    note?: string;
    cue?: string;
    role?: string;
  };
};

type Props = {
  protocol: Protocol | null | undefined;
};

/** Multi-step coaching card: entry + next/fallback + optional full progression. */
export default function CoachingProtocolCard({ protocol }: Props) {
  const [openAll, setOpenAll] = useState(false);
  if (!protocol || !(protocol.steps || []).length) return null;

  const entry = protocol.entry_step || protocol.steps?.[0] || {};
  const level = entry.level || protocol.entry_level || 1;
  const success = (entry.success_cues || []).slice(0, 4);
  const nextPreview = entry.next_preview || protocol.if_better;
  const regressPreview = entry.regress_preview || protocol.if_worse;
  const transfer = protocol.song_transfer;
  const overlay = protocol.target_overlay;

  return (
    <section className="section" data-testid="coaching-protocol">
      <h3 className="section-title">이번에 먼저 해볼 것</h3>
      <p className="body-text" style={{ fontWeight: 700, margin: 0 }}>
        {level}단계 · {scrubUserText(entry.title || '')}
      </p>
      {entry.instruction ? (
        <p className="body-text muted" style={{ marginTop: 8, lineHeight: 1.55 }}>
          {scrubUserText(entry.instruction)}
        </p>
      ) : null}
      {entry.repetitions ? (
        <p className="body-text muted" style={{ marginTop: 6, fontSize: '0.92rem' }}>
          반복 · {scrubUserText(entry.repetitions)}
        </p>
      ) : null}

      {success.length > 0 ? (
        <>
          <p className="eyebrow" style={{ marginTop: 12 }}>잘 되고 있다는 신호</p>
          <ul className="body-text" style={{ paddingLeft: 18, margin: 0 }}>
            {success.map((c) => (
              <li key={c}>{scrubUserText(c)}</li>
            ))}
          </ul>
        </>
      ) : null}

      <div className="protocol-branch" data-testid="protocol-next">
        <p className="eyebrow" style={{ marginTop: 12 }}>잘 되면</p>
        <p className="body-text" style={{ margin: 0, lineHeight: 1.45 }}>
          → {scrubUserText(nextPreview || '다음 단계로 진행')}
        </p>
      </div>
      <div className="protocol-branch" data-testid="protocol-regress">
        <p className="eyebrow" style={{ marginTop: 10 }}>잘 안 되면</p>
        <p className="body-text" style={{ margin: 0, lineHeight: 1.45 }}>
          → {scrubUserText(regressPreview || '한 단계 쉬운 범위로')}
        </p>
      </div>

      {transfer?.instruction ? (
        <div data-testid="protocol-song-transfer" style={{ marginTop: 14 }}>
          <p className="eyebrow">노래에 적용</p>
          <p className="body-text muted" style={{ margin: 0, lineHeight: 1.5 }}>
            {scrubUserText(transfer.instruction)}
          </p>
        </div>
      ) : null}

      {overlay?.note || overlay?.cue ? (
        <p className="body-text muted" style={{ marginTop: 12, lineHeight: 1.5, fontSize: '0.92rem' }}>
          {scrubUserText(overlay.note || overlay.cue || '')}
        </p>
      ) : null}

      {(protocol.steps || []).length > 1 ? (
        <div style={{ marginTop: 14 }}>
          <button
            type="button"
            className="btn secondary"
            data-testid="protocol-expand"
            onClick={() => setOpenAll((v) => !v)}
            style={{ fontSize: '0.9rem', padding: '8px 12px' }}
          >
            {openAll ? '단계 접기' : '다음 단계 보기'}
          </button>
          {openAll ? (
            <div data-testid="protocol-all-steps" style={{ marginTop: 12 }}>
              {(protocol.steps || []).map((s) => (
                <div key={s.id || s.level} className="protocol-step" style={{ marginBottom: 14 }}>
                  <p style={{ margin: 0, fontWeight: 700 }}>
                    {s.level}단계 · {scrubUserText(s.title || '')}
                  </p>
                  {s.instruction ? (
                    <p className="body-text muted" style={{ margin: '6px 0 0', lineHeight: 1.5 }}>
                      {scrubUserText(s.instruction)}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

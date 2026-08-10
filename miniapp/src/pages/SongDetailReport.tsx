import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  getPreviewUrl,
  getProducts,
  getSongDetailedReport,
  patchHistory,
} from '../api/client';

function seekTo(audio: HTMLAudioElement | null, sec?: number | null) {
  if (!audio || sec == null || Number.isNaN(Number(sec))) return;
  audio.currentTime = Math.max(0, Number(sec));
  void audio.play();
}

function ScoreLine({
  score,
  label,
}: {
  score?: number | null;
  label?: string;
}) {
  if (score == null) {
    return (
      <strong>
        — · <span className="muted" style={{ fontWeight: 500 }}>{label || '—'}</span>
      </strong>
    );
  }
  return (
    <strong>
      {Math.round(score)}점
      <span className="muted" style={{ marginLeft: 8, fontWeight: 500 }}>
        · {label}
      </span>
    </strong>
  );
}

/** 0 = light (left), 1 = firm (right) */
export function ContactContinuum({ value }: { value: number }) {
  const c = Math.max(0, Math.min(1, Number(value)));
  const left = Math.max(0, Math.round(c * 6));
  const right = Math.max(0, Math.round((1 - c) * 6));
  return (
    <p className="muted" style={{ margin: '4px 0', fontSize: '0.9rem' }}>
      가벼움 {'─'.repeat(left)}●{'─'.repeat(right)} 단단함
      <br />
      (좋고 나쁨이 아닌 경향 표시)
    </p>
  );
}

export default function SongDetailReport() {
  const { id } = useParams();
  const nav = useNavigate();
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [diagPrice, setDiagPrice] = useState('—');
  const [diagProduct, setDiagProduct] = useState('diagnostic_upgrade');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrl = useMemo(() => sessionStorage.getItem('vocalfb_last_blob'), []);
  const previewUrl = id ? getPreviewUrl(id) : '';

  useEffect(() => {
    if (!id) return;
    getSongDetailedReport(id)
      .then((r) => {
        if (r.error === 'SONG_DETAIL_LOCKED') {
          setError('SONG_DETAIL_LOCKED');
          return;
        }
        setReport(r);
        patchHistory(id, { songDetailUnlocked: true });
      })
      .catch((e) => setError(e.message));
    getProducts(id).then((cat) => {
      const offer = cat.offers?.diagnostic || 'diagnostic_full';
      setDiagProduct(offer);
      setDiagPrice(cat.products?.[offer]?.display_amount || '—');
    }).catch(() => undefined);
  }, [id]);

  if (error === 'SONG_DETAIL_LOCKED') {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.5rem' }}>상세 리포트 잠금</h1>
        <p className="lead">이 노래의 상세 리포트가 아직 해제되지 않았어요.</p>
        <Link className="btn" to={`/result/${id}`}>결과로 돌아가기</Link>
      </main>
    );
  }
  if (error) return <main><p className="fail">{error}</p></main>;
  if (!report) return <main><p className="muted">상세 리포트 불러오는 중…</p></main>;

  const summary = report.summary || {};
  const decision = report.coaching_decision || report.vocal_function_profile?.coaching_decision || {};
  const vf = report.vocal_function_profile || {};
  const dims = vf.dimensions || [];
  const focus = report.focus_segments || report.timeline || [];
  const supplement = report.performance_supplement || {};
  const suppAreas = supplement.areas || report.areas || [];
  const extraMeasure = report.additional_measurements || [];
  const primary = decision.primary_bottleneck;
  const preserve = decision.preserve || [];
  const modify = decision.modify || [];
  const why = decision.why || [];

  return (
    <main>
      <Link className="muted" to={`/result/${id}`}>← 무료 결과</Link>
      <h1 className="brand" style={{ fontSize: '1.6rem', marginTop: 12 }}>
        {summary.title || '오늘의 핵심'}
      </h1>
      <p className="lead">{summary.text || decision.headline}</p>
      {(vf.quality_badge || report.quality_badge) && (
        <p className="muted" style={{ fontSize: '0.9rem' }}>
          분석 신뢰 범위: {vf.quality_badge || report.quality_badge}
        </p>
      )}
      {vf.separation_note && (
        <p className="muted" style={{ fontSize: '0.85rem' }}>{vf.separation_note}</p>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>가장 먼저 바꿔볼 부분</h3>
        {!primary && modify.length === 0 && (
          <p className="muted">이번 녹음에서 우선 수정 후보는 제한적이에요.</p>
        )}
        {(modify.length ? modify : primary ? [{ label: primary.user_title, why: primary.why }] : []).map(
          (m: any, i: number) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div className="area-row">
                <span>{m.label || primary?.user_title}</span>
                <strong>MODIFY</strong>
              </div>
              <p className="muted" style={{ margin: '4px 0' }}>{m.why || primary?.why}</p>
            </div>
          ),
        )}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>지금 유지할 부분</h3>
        {preserve.length === 0 && <p className="muted">표시할 유지 항목이 없어요.</p>}
        {preserve.map((p: any) => (
          <div key={p.id} style={{ marginBottom: 8 }}>
            <div className="area-row">
              <span>✓ {p.label}</span>
              <strong>PRESERVE</strong>
            </div>
            {p.why && <p className="muted" style={{ margin: '2px 0', fontSize: '0.9rem' }}>{p.why}</p>}
          </div>
        ))}
      </div>

      {why.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>왜 그렇게 판단했나요?</h3>
          {why.map((w: string, i: number) => (
            <p key={i} className="muted" style={{ margin: '6px 0' }}>{w}</p>
          ))}
          {primary?.alternative_explanations?.length ? (
            <p className="muted" style={{ fontSize: '0.85rem' }}>
              다른 설명 후보: {(primary.alternative_explanations || []).join(', ')}
            </p>
          ) : null}
        </div>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>다시 들어볼 구간</h3>
        <audio ref={audioRef} src={blobUrl || previewUrl} controls style={{ width: '100%' }} />
        {focus.length === 0 && <p className="muted">표시할 구간이 없어요.</p>}
        {focus.map((ev: any, i: number) => (
          <div key={i} style={{ marginTop: 12 }}>
            <div className="area-row">
              <span>
                {ev.time_label
                  || (ev.original_start_sec != null
                    ? `${Number(ev.original_start_sec).toFixed(1)}s – ${Number(ev.original_end_sec ?? ev.original_start_sec).toFixed(1)}s`
                    : `${Number(ev.start_sec).toFixed(1)}s – ${Number(ev.end_sec).toFixed(1)}s`)}
                {ev.headline ? ` · ${ev.headline}` : ''}
              </span>
              <button
                type="button"
                className="btn secondary"
                style={{ fontSize: '0.8rem', padding: '6px 10px' }}
                onClick={() =>
                  seekTo(
                    audioRef.current,
                    ev.original_start_sec ?? ev.start_sec,
                  )
                }
              >
                듣기
              </button>
            </div>
            <p className="muted" style={{ margin: '4px 0' }}>
              {ev.user_message || ev.what_user_may_hear}
            </p>
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>오늘의 연습</h3>
        <ul>
          {(report.training_plan || []).map((x: string, i: number) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
        {(decision.success_criteria || []).length > 0 && (
          <>
            <p className="muted" style={{ marginTop: 8 }}>성공 기준</p>
            <ul className="muted">
              {(decision.success_criteria || []).map((x: string, i: number) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>성대 작동 프로필</h3>
        {dims.length === 0 && (
          <p className="muted">신뢰도 있게 표시할 프로필 항목이 제한적이에요.</p>
        )}
        {dims.map((d: any) => (
          <div key={d.dimension_id} style={{ marginBottom: 18 }}>
            <div className="area-row">
              <span>{d.display_name}</span>
              <strong>{d.continuum_label || d.status_label || d.prevalence_label}</strong>
            </div>
            {d.dimension_id === 'glottal_contact_profile' && d.continuum_0_to_1 != null && (
              <ContactContinuum value={d.continuum_0_to_1} />
            )}
            {d.profile && d.dimension_id === 'resonance_formant_strategy' ? (
              <ul className="muted" style={{ margin: '6px 0', paddingLeft: 18 }}>
                <li>밝기: {d.profile.brightness}</li>
                <li>중역 존재감: {d.profile.mid_presence}</li>
              </ul>
            ) : (
              <p className="muted" style={{ margin: '4px 0' }}>{d.summary}</p>
            )}
            {d.what_it_may_mean && (
              <p className="muted" style={{ margin: '4px 0', fontSize: '0.9rem' }}>
                {d.what_it_may_mean}
              </p>
            )}
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{supplement.title || '보조 가창 분석'}</h3>
        <p className="muted">{supplement.note || '가창 참고 정보입니다.'}</p>
        {suppAreas.map((a: any) => (
          <div key={a.area_id} style={{ marginBottom: 12 }}>
            <div className="area-row">
              <span>{a.display_name}</span>
              <ScoreLine score={a.score} label={a.status_label || a.status} />
            </div>
            {a.headline && <p className="muted" style={{ margin: '4px 0' }}>{a.headline}</p>}
          </div>
        ))}
      </div>

      {extraMeasure.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>추가 정밀 측정</h3>
          <ul className="muted">
            {extraMeasure.map((m: any, i: number) => (
              <li key={i}>{m.reason}: {(m.tasks || []).join(', ')}</li>
            ))}
          </ul>
        </div>
      )}

      {report.unknown_footer && (
        <p className="muted" style={{ fontSize: '0.85rem' }}>{report.unknown_footer}</p>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>한계</h3>
        <ul className="muted">
          {(report.limitations || []).map((x: string, i: number) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
        <p className="muted" style={{ fontSize: '0.85rem' }}>{report.disclaimer}</p>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{report.upgrade?.title || '정밀 진단'}</h3>
        <p className="muted">{report.upgrade?.body}</p>
        <button
          type="button"
          className="btn"
          onClick={() => nav(`/premium?analysisId=${id}&product=${diagProduct}`)}
        >
          {report.upgrade?.cta || '정밀 발성 진단'} ({diagPrice})
        </button>
      </div>
    </main>
  );
}

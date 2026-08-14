import { useEffect, useRef, useState, type RefObject } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  getAnalysisAccess,
  getProducts,
  getSongDetailedReport,
  patchHistory,
} from '../api/client';
import { formatSecRange, useIsDebug } from '../lib/reportPresentation';
import VocalTypeHero from '../components/report/VocalTypeHero';
import MainDiagnosis from '../components/report/MainDiagnosis';
import VocalProfile from '../components/report/VocalProfile';
import HighNoteFunctionSection from '../components/report/HighNoteFunctionSection';
import TimbreProfileSection from '../components/report/TimbreProfileSection';
import AudioCompare from '../components/report/AudioCompare';
import MoreDetails from '../components/report/MoreDetails';
import DiagnosticCTA from '../components/report/DiagnosticCTA';
import ReportAudioPlayer, { type ClipRange } from '../components/report/ReportAudioPlayer';

export default function SongDetailReport() {
  const { id } = useParams();
  const debug = useIsDebug();
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [diagPrice, setDiagPrice] = useState('—');
  const [diagProduct, setDiagProduct] = useState('diagnostic_upgrade');
  const [clip, setClip] = useState<ClipRange | null>(null);
  const [accessState, setAccessState] = useState<{
    diagnostic_unlocked?: boolean;
    diagnostic_session_id?: string | null;
  }>({});
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!id) return;
    getSongDetailedReport(id)
      .then((r) => {
        if (r.error === 'SONG_DETAIL_LOCKED') {
          setError('SONG_DETAIL_LOCKED');
          return;
        }
        setReport(r);
        const vt = r.vocal_type_profile || r.vocal_function_profile?.vocal_type_profile;
        patchHistory(id, {
          songDetailUnlocked: true,
          vocalType: vt?.display_name || vt?.headline || undefined,
          filename: sessionStorage.getItem('vocalfb_last_filename') || undefined,
        });
        if (r.access) setAccessState(r.access);
      })
      .catch((e) => setError(e.message));
    getProducts(id)
      .then((cat) => {
        const offer = cat.offers?.diagnostic || 'diagnostic_full';
        setDiagProduct(offer);
        setDiagPrice(cat.products?.[offer]?.display_amount || '—');
      })
      .catch(() => undefined);
    getAnalysisAccess(id)
      .then((a) =>
        setAccessState((prev) => ({
          ...prev,
          diagnostic_unlocked: a.diagnostic_unlocked,
          diagnostic_session_id: a.diagnostic_session_id,
        })),
      )
      .catch(() => undefined);
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
  if (error) {
    return (
      <main>
        <p className="fail">{error}</p>
      </main>
    );
  }
  if (!report) {
    return (
      <main>
        <p className="muted">리포트 불러오는 중…</p>
        <div className="skeleton" style={{ height: 28, width: '55%' }} />
        <div className="skeleton" style={{ height: 120 }} />
        <div className="skeleton" style={{ height: 80 }} />
      </main>
    );
  }

  const decision = report.coaching_decision || report.vocal_function_profile?.coaching_decision || {};
  const vf = report.vocal_function_profile || {};
  const dims = vf.dimensions || [];
  const observationFocus = report.observation_segments || [];
  const supplement = report.performance_supplement || {};
  const suppAreas = supplement.areas || report.areas || [];
  const primary = decision.primary_bottleneck;
  const preserve = decision.preserve || [];
  const bestSelf = decision.best_self_reference;
  const targetEp = decision.target_episode;
  const coreSpan = targetEp?.core_evidence_span;
  const criteriaMatrix = report.criteria_matrix || vf.criteria_matrix || [];
  const candidateComparison = decision.candidate_comparison || [];
  const vocalType = report.vocal_type_profile || vf.vocal_type_profile;
  const vocalStyle = report.vocal_style_profile || vf.vocal_style_profile;
  const canonicalRegister =
    vocalStyle?.canonical_register
    || vocalType?.canonical_register
    || vocalType?.register_strategy;
  const canonicalAcoustic =
    report.canonical_acoustic_axes
    || vocalStyle?.canonical_acoustic_axes
    || vf.canonical_acoustic_axes;
  const effortAssessment =
    report.effort_assessment
    || vf.effort_assessment
    || (Array.isArray(dims)
      ? dims.find((d: any) => d?.dimension_id === 'vocal_effort_strain')?.effort_assessment
      : (dims as any)?.vocal_effort_strain?.effort_assessment);

  function playEpisode(ev: any) {
    const start = Number(ev?.original_start_sec ?? ev?.start_sec);
    const endRaw = ev?.original_end_sec ?? ev?.end_sec;
    const end = endRaw != null ? Number(endRaw) : null;
    if (Number.isNaN(start)) return;
    const range = formatSecRange(start, end ?? undefined);
    setClip({
      start_sec: start,
      end_sec: end,
      label: range ? `선택한 구간 · ${range}` : '선택한 구간',
    });
  }

  function playFullRecording() {
    setClip({ start_sec: 0, end_sec: null, label: '원본 녹음' });
  }

  return (
    <main style={{ paddingBottom: clip ? 28 : 12 }}>
      <Link className="muted" to={`/result/${id}`}>‹ 무료 결과</Link>
      <p className="page-kicker" style={{ marginTop: 14 }}>상세 리포트</p>
      <h1 className="brand" style={{ fontSize: '1.4rem', marginTop: 0, marginBottom: 0 }}>
        더 자세히 살펴보기
      </h1>
      <p className="muted body-text" style={{ marginTop: 6 }}>
        현재 노래를 더 자세히 분석한 결과예요. 추가 녹음은 없어요.
      </p>

      <div className="card" style={{ marginTop: 12, marginBottom: 12 }}>
        <button type="button" className="btn secondary" onClick={playFullRecording}>
          원본 녹음 듣기
        </button>
      </div>

      <VocalTypeHero profile={vocalType} styleProfile={vocalStyle} />

      <MainDiagnosis
        primary={primary}
        coreSpan={coreSpan}
        onPlay={playEpisode}
        showAudio
        effortAssessment={effortAssessment}
      />

      <VocalProfile
        dimensions={dims}
        criteriaMatrix={criteriaMatrix}
        canonicalRegister={canonicalRegister}
        canonicalAcoustic={canonicalAcoustic}
      />

      <HighNoteFunctionSection
        profile={report.high_note_function_profile || vf.high_note_function_profile}
      />
      <TimbreProfileSection profile={report.timbre_profile || vf.timbre_profile} omitPresence />

      <AudioCompare
        featureClip={coreSpan || null}
        compareClip={bestSelf || null}
        onPlay={playEpisode}
      />

      <MoreDetails
        vocalType={vocalType}
        criteriaMatrix={criteriaMatrix}
        dimensions={dims}
        observationFocus={observationFocus}
        preserve={preserve}
        performanceAreas={suppAreas}
        disclaimer={report.disclaimer}
        debug={debug}
        candidateComparison={candidateComparison}
      />

      <DiagnosticCTA
        analysisId={id}
        priceLabel={diagPrice}
        productId={diagProduct}
        unlocked={!!accessState.diagnostic_unlocked}
        sessionId={accessState.diagnostic_session_id}
        diagnosticOffer={
          report.diagnostic_offer ||
          report.vocal_function_profile?.diagnostic_offer ||
          null
        }
      />

      {id ? (
        <ReportAudioPlayer
          analysisId={id}
          audioRef={audioRef as RefObject<HTMLAudioElement>}
          clip={clip}
          onClipClear={() => setClip(null)}
        />
      ) : null}
    </main>
  );
}

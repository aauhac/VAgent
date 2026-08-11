import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  getPreviewUrl,
  getProducts,
  getSongDetailedReport,
  patchHistory,
} from '../api/client';
import { formatSecRange, useIsDebug } from '../lib/reportPresentation';
import VocalTypeHero from '../components/report/VocalTypeHero';
import MainDiagnosis from '../components/report/MainDiagnosis';
import VocalProfile from '../components/report/VocalProfile';
import AudioCompare from '../components/report/AudioCompare';
import MoreDetails from '../components/report/MoreDetails';
import DiagnosticCTA from '../components/report/DiagnosticCTA';
import StickyAudioPlayer from '../components/report/StickyAudioPlayer';

function seekTo(audio: HTMLAudioElement | null, sec?: number | null) {
  if (!audio || sec == null || Number.isNaN(Number(sec))) return;
  audio.currentTime = Math.max(0, Number(sec));
  void audio.play();
}

export default function SongDetailReport() {
  const { id } = useParams();
  const debug = useIsDebug();
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [diagPrice, setDiagPrice] = useState('—');
  const [diagProduct, setDiagProduct] = useState('diagnostic_upgrade');
  const [playerLabel, setPlayerLabel] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrl = useMemo(() => sessionStorage.getItem('vocalfb_last_blob'), []);
  const previewUrl = id ? getPreviewUrl(id) : '';
  const audioSrc = blobUrl || previewUrl;

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
      })
      .catch((e) => setError(e.message));
    getProducts(id)
      .then((cat) => {
        const offer = cat.offers?.diagnostic || 'diagnostic_full';
        setDiagProduct(offer);
        setDiagPrice(cat.products?.[offer]?.display_amount || '—');
      })
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
  const access = report.access || {};

  function playEpisode(ev: any) {
    const raw = Number(ev?.original_start_sec ?? ev?.start_sec);
    if (Number.isNaN(raw)) return;
    const range = formatSecRange(
      ev?.original_start_sec ?? ev?.start_sec,
      ev?.original_end_sec ?? ev?.end_sec,
    );
    setPlayerLabel(range ? `선택한 구간 · ${range}` : '선택한 구간');
    seekTo(audioRef.current, Math.max(0, raw - 0.7));
  }

  return (
    <main style={{ paddingBottom: playerLabel ? 28 : 12 }}>
      <Link className="muted" to={`/result/${id}`}>‹ 무료 결과</Link>
      <p className="page-kicker" style={{ marginTop: 14 }}>상세 리포트</p>
      <h1 className="brand" style={{ fontSize: '1.4rem', marginTop: 0, marginBottom: 0 }}>
        더 자세히 살펴보기
      </h1>

      <VocalTypeHero profile={vocalType} />

      <MainDiagnosis
        primary={primary}
        coreSpan={coreSpan}
        onPlay={playEpisode}
        showAudio
      />

      <VocalProfile dimensions={dims} criteriaMatrix={criteriaMatrix} />

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
        unlocked={!!access.diagnostic_unlocked}
        sessionId={access.diagnostic_session_id}
        diagnosticOffer={
          report.diagnostic_offer ||
          report.vocal_function_profile?.diagnostic_offer ||
          null
        }
      />

      <StickyAudioPlayer
        src={audioSrc}
        label={playerLabel}
        audioRef={audioRef as RefObject<HTMLAudioElement>}
        active={!!playerLabel}
      />
    </main>
  );
}

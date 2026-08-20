import { useEffect } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import Home from './pages/Home';
import Record from './pages/Record';
import Upload from './pages/Upload';
import QualityResult from './pages/QualityResult';
import Analyzing from './pages/Analyzing';
import Result from './pages/Result';
import SongDetailReport from './pages/SongDetailReport';
import History from './pages/History';
import PremiumUnlock from './pages/PremiumUnlock';
import ConcernIntake from './pages/ConcernIntake';
import SafetyCheck from './pages/SafetyCheck';
import DiagnosticRecordingIntro from './pages/DiagnosticRecordingIntro';
import DiagnosticTask from './pages/DiagnosticTask';
import PremiumReport from './pages/PremiumReport';
import DiagnosticResume from './pages/DiagnosticResume';
import ProgressInsight from './pages/ProgressInsight';
import ServiceInfo from './pages/ServiceInfo';
import { LegalPrivacy, LegalPrivacyConsent, LegalTerms } from './pages/Legal';
import { SESSION_CLEARED_EVENT } from './lib/clientSession';
import { bootstrapTossSession, getVagentSessionToken, resumeTossSession } from './lib/tossAuth';
import { recoverPendingPurchases } from './lib/tossIap';
import { getUserIdentity } from './lib/userIdentity';

function afterFirstPaint(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });
}

function MiniappRuntime() {
  const nav = useNavigate();

  useEffect(() => {
    let cancelled = false;
    const boot = async () => {
      await afterFirstPaint();
      if (cancelled) return;
      await getUserIdentity().catch(() => undefined);
      await bootstrapTossSession();
      if (cancelled) return;
      if (getVagentSessionToken()) {
        await recoverPendingPurchases().catch(() => undefined);
      }
    };
    void boot();

    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      void resumeTossSession().catch(() => undefined);
    };
    const onCleared = () => {
      nav('/', { replace: true });
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener(SESSION_CLEARED_EVENT, onCleared);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener(SESSION_CLEARED_EVENT, onCleared);
    };
  }, [nav]);

  return null;
}

export default function App() {
  return (
    <div className="app-shell">
      <MiniappRuntime />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/record" element={<Record />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/quality" element={<QualityResult />} />
        <Route path="/analyzing/:id" element={<Analyzing />} />
        <Route path="/result/:id" element={<Result />} />
        <Route path="/result/:id/detail" element={<SongDetailReport />} />
        <Route path="/progress" element={<ProgressInsight />} />
        <Route path="/history" element={<History />} />
        <Route path="/service-info" element={<ServiceInfo />} />
        <Route path="/premium" element={<PremiumUnlock />} />
        <Route path="/legal/terms" element={<LegalTerms />} />
        <Route path="/legal/privacy" element={<LegalPrivacy />} />
        <Route path="/legal/privacy-consent" element={<LegalPrivacyConsent />} />
        <Route path="/diagnostic/:sessionId/concerns" element={<ConcernIntake />} />
        <Route path="/diagnostic/:sessionId/safety" element={<SafetyCheck />} />
        <Route path="/diagnostic/:sessionId/recordings" element={<DiagnosticRecordingIntro />} />
        <Route path="/diagnostic/:sessionId/task/:taskId" element={<DiagnosticTask />} />
        <Route path="/diagnostic/:sessionId/report" element={<PremiumReport />} />
        {/* Keep any diagnostic session URL in-flow — never dump to Home */}
        <Route path="/diagnostic/:sessionId/*" element={<DiagnosticResume />} />
        <Route path="/diagnostic/:sessionId" element={<DiagnosticResume />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

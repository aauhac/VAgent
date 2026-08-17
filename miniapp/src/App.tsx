import { Navigate, Route, Routes } from 'react-router-dom';
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
import { LegalPrivacy, LegalPrivacyConsent, LegalTerms } from './pages/Legal';

export default function App() {
  return (
    <div className="app-shell">
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

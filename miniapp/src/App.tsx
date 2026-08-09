import { Navigate, Route, Routes } from 'react-router-dom';
import Home from './pages/Home';
import Record from './pages/Record';
import Upload from './pages/Upload';
import QualityResult from './pages/QualityResult';
import Analyzing from './pages/Analyzing';
import Result from './pages/Result';
import History from './pages/History';

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
        <Route path="/history" element={<History />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

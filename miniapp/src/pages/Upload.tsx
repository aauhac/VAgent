import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createAnalysis } from '../api/client';

export default function Upload() {
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [separate, setSeparate] = useState(false);

  async function onFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const { analysis_id } = await createAnalysis(file, file.name, { separate });
      sessionStorage.setItem('vocalfb_last_blob', URL.createObjectURL(file));
      nav(`/analyzing/${analysis_id}`);
    } catch (e: any) {
      setError(e?.message || '업로드 실패');
      setBusy(false);
    }
  }

  return (
    <main>
      <Link className="muted" to="/">← 홈</Link>
      <h1 className="brand" style={{ fontSize: '1.8rem', marginTop: 16 }}>파일 업로드</h1>
      <p className="lead">m4a / mp3 / wav 등 노래 음성 파일을 올려 주세요.</p>
      <div className="panel">
        <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input type="checkbox" checked={separate} onChange={(e) => setSeparate(e.target.checked)} />
          반주 포함 음원이면 보컬 분리 시도 (선택)
        </label>
        <input
          style={{ marginTop: 16, width: '100%' }}
          type="file"
          accept="audio/*,.m4a,.mp3,.wav,.flac,.aac,.webm"
          disabled={busy}
          onChange={(e) => onFile(e.target.files?.[0] || null)}
        />
        {busy && <p className="muted">업로드 중…</p>}
        {error && <p className="fail">{error}</p>}
      </div>
    </main>
  );
}

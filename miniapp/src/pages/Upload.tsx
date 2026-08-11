import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createAnalysis } from '../api/client';

export default function Upload() {
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pureVocal, setPureVocal] = useState(false);

  async function onFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      // analysis_mode and input_mode are independent:
      // pure vocal still gets FUNCTIONAL coaching (without Demucs)
      const { analysis_id } = await createAnalysis(file, file.name, {
        analysis_mode: 'FUNCTIONAL',
        input_mode: pureVocal ? 'VOCAL_ONLY' : 'AUTO',
        separate: !pureVocal,
      });
      sessionStorage.setItem('vocalfb_last_blob', URL.createObjectURL(file));
      sessionStorage.setItem('vocalfb_last_filename', file.name);
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
      <p className="lead">
        m4a / mp3 / wav 등 노래 음성 파일을 올려 주세요. 기본으로 기능적 발성 분석을 위해 보컬 분리를 시도해요.
      </p>
      <div className="panel">
        <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={pureVocal}
            onChange={(e) => setPureVocal(e.target.checked)}
          />
          반주 없는 순수 보컬만 녹음했어요 (고급)
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

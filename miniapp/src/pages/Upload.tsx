import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createAnalysis } from '../api/client';
import AccompanimentToggle, {
  analysisOptsFromAccompaniment,
} from '../components/ui/AccompanimentToggle';
import AudioReadyPanel from '../components/ui/AudioReadyPanel';

type ReadyFile = {
  file: File;
  url: string;
};

export default function Upload() {
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hasAccompaniment, setHasAccompaniment] = useState(false);
  const [ready, setReady] = useState<ReadyFile | null>(null);

  useEffect(() => () => {
    if (ready?.url) URL.revokeObjectURL(ready.url);
  }, [ready?.url]);

  function onPick(file: File | null) {
    if (!file) return;
    setError(null);
    if (ready?.url) URL.revokeObjectURL(ready.url);
    setReady({ file, url: URL.createObjectURL(file) });
  }

  function clearFile() {
    if (ready?.url) URL.revokeObjectURL(ready.url);
    setReady(null);
    setError(null);
  }

  async function analyze() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const opts = analysisOptsFromAccompaniment(hasAccompaniment);
      const { analysis_id } = await createAnalysis(ready.file, ready.file.name, opts);
      sessionStorage.setItem('vocalfb_last_blob', URL.createObjectURL(ready.file));
      sessionStorage.setItem('vocalfb_last_filename', ready.file.name);
      sessionStorage.setItem('vocalfb_last_has_accompaniment', hasAccompaniment ? '1' : '0');
      nav(`/analyzing/${analysis_id}`);
    } catch (e: any) {
      setError(e?.message || '업로드 실패');
      setBusy(false);
    }
  }

  return (
    <main>
      <Link className="muted" to="/">← 홈</Link>
      <p className="page-kicker" style={{ marginTop: 16 }}>업로드</p>
      <h1 className="brand" style={{ fontSize: '1.7rem' }}>파일로 분석하기</h1>
      <p className="lead">
        파일을 올린 뒤 미리듣기로 확인한 다음 분석해요. 기본은 무반주(순수 보컬) 분석입니다.
      </p>

      <div className="panel">
        <AccompanimentToggle
          checked={hasAccompaniment}
          onChange={setHasAccompaniment}
          noun="파일"
          disabled={busy}
        />

        {!ready ? (
          <>
            <ul className="record-idle-tips">
              <li>지원 형식: m4a, mp3, wav, flac, aac, webm</li>
              <li>권장 길이 15~60초 · 한 구절 정도가 좋아요</li>
              <li>반주가 섞여 있으면 위 체크박스를 켜 주세요</li>
            </ul>
            <label className="btn secondary" style={{ width: '100%', cursor: 'pointer' }}>
              파일 선택
              <input
                type="file"
                accept="audio/*,.m4a,.mp3,.wav,.flac,.aac,.webm"
                disabled={busy}
                style={{ display: 'none' }}
                onChange={(e) => onPick(e.target.files?.[0] || null)}
              />
            </label>
          </>
        ) : (
          <AudioReadyPanel
            src={ready.url}
            title="업로드 완료"
            subtitle={ready.file.name}
            onClear={clearFile}
            clearLabel="다시 선택"
            onAnalyze={analyze}
            analyzing={busy}
          />
        )}

        {error && <p className="fail" style={{ marginTop: 12, marginBottom: 0 }}>{error}</p>}
      </div>
    </main>
  );
}

import { formatSecRange } from '../../lib/reportCopy';

type Clip = {
  key: string;
  label: string;
  start?: number | null;
  end?: number | null;
  payload: any;
};

type Props = {
  featureClip?: any;
  compareClip?: any;
  onPlay: (ev: any) => void;
};

export default function AudioCompare({ featureClip, compareClip, onPlay }: Props) {
  const clips: Clip[] = [];
  if (featureClip) {
    clips.push({
      key: 'feature',
      label: '특징이 잘 드러난 구간',
      start: featureClip.original_start_sec ?? featureClip.start_sec,
      end: featureClip.original_end_sec ?? featureClip.end_sec,
      payload: featureClip,
    });
  }
  if (compareClip) {
    clips.push({
      key: 'compare',
      label: '비교해서 들어볼 구간',
      start: compareClip.original_start_sec ?? compareClip.start_sec,
      end: compareClip.original_end_sec ?? compareClip.end_sec,
      payload: compareClip,
    });
  }
  if (clips.length === 0) return null;

  return (
    <section className="section">
      <h3 className="section-title">특징 구간 듣기</h3>
      {clips.map((c) => {
        const range = formatSecRange(c.start, c.end);
        return (
          <div key={c.key} style={{ marginBottom: 14 }}>
            <p style={{ margin: '0 0 6px', fontWeight: 600 }}>{c.label}</p>
            <div className="audio-chip-row">
              <button type="button" className="btn chip secondary" onClick={() => onPlay(c.payload)}>
                ▶ {range || '들어보기'}
              </button>
            </div>
          </div>
        );
      })}
    </section>
  );
}

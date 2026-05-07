import json
from collections import Counter

with open(r'c:\VocalAgent\outputs\거의동116_feedback_20260507_012327\analysis.json', encoding='utf-8') as f:
    d = json.load(f)

print('=== WAVEFORM FEATURES ===')
wf = d['waveform_features']
print(f'  rms_mean: {wf["rms_mean"]:.6f}')
print(f'  rms_max: {wf["rms_max"]:.6f}')
print(f'  peak_amplitude: {wf["peak_amplitude"]:.4f}')
print(f'  dynamic_range_db: {wf["dynamic_range_db"]:.2f} dB')
print(f'  silent_ratio: {wf["silent_ratio"]:.3f}')

print()
print('=== FREQUENCY FEATURES ===')
ff = d['frequency_features']
print(f'  spectral_centroid_mean_hz: {ff["spectral_centroid_mean_hz"]:.1f} Hz')
print(f'  spectral_bandwidth_mean_hz: {ff["spectral_bandwidth_mean_hz"]:.1f} Hz')
print(f'  spectral_rolloff_mean_hz: {ff["spectral_rolloff_mean_hz"]:.1f} Hz')
print(f'  dominant_frequency_hz: {ff["dominant_frequency_hz"]:.1f} Hz')
print('  band_energy_db:')
for band, val in ff['band_energy_db'].items():
    print(f'    {band}: {val}')

print()
print('=== PITCH FEATURES ===')
pf = d['pitch_features']
print(f'  f0_mean_hz: {pf["f0_mean_hz"]:.2f}')
print(f'  f0_min_hz: {pf["f0_min_hz"]:.2f}')
print(f'  f0_max_hz: {pf["f0_max_hz"]:.2f}')
print(f'  f0_std_hz: {pf["f0_std_hz"]:.2f}')
print(f'  voiced_ratio: {pf["voiced_ratio"]:.3f}')
print(f'  pitch_stability_cents: {pf["pitch_stability_cents"]:.2f}')

print()
print('=== TIMBRE FEATURES ===')
tf = d['timbre_features']
for k, v in tf.items():
    print(f'  {k}: {v:.4f}')

print()
print('=== QUALITY REPORT ===')
qr = d['quality_report']
for k, v in qr.items():
    print(f'  {k}: {v}')

print()
print('=== DETECTED ISSUES ===')
for issue in d['detected_issues']:
    print(f'  {issue}')

print()
print('=== ISSUE EVENTS (type별 개수) ===')
cnt = Counter(e['type'] for e in d['issue_events'])
for t, n in cnt.items():
    print(f'  {t}: {n}개')

print()
print('=== ISSUE EVENTS (severity별) ===')
sev = Counter(e['severity'] for e in d['issue_events'])
for s, n in sev.items():
    print(f'  {s}: {n}개')

# 볼륨 드롭 이벤트 출력
print()
print('=== VOLUME DROP EVENTS ===')
vol_drops = [e for e in d['issue_events'] if e['type'] == 'volume_drop']
for e in vol_drops[:20]:
    det = e.get('detail', {})
    print(f"  {e['start']:.2f}s~{e['end']:.2f}s | {e['severity']} | rms_before={det.get('rms_before',0):.5f} rms_after={det.get('rms_after',0):.5f} ratio={det.get('ratio',0):.3f}")

# 불안정 pitch 이벤트 상위 10개 (편차 큰 것)
print()
print('=== UNSTABLE PITCH EVENTS (편차 큰 순, top 10) ===')
pitch_events = [e for e in d['issue_events'] if e['type'] == 'unstable_pitch']
pitch_events.sort(key=lambda x: x.get('detail', {}).get('avg_deviation_cents', 0), reverse=True)
for e in pitch_events[:10]:
    det = e.get('detail', {})
    dur = e['end'] - e['start']
    print(f"  {e['start']:.2f}s~{e['end']:.2f}s (dur={dur:.2f}s) | {e['severity']} | deviation={det.get('avg_deviation_cents',0):.1f}cents")

# per_100ms_summary로 볼륨 드롭 직접 탐색
print()
print('=== PER_100MS RMS 분포 분석 ===')
p100 = wf.get('per_100ms_summary', [])
rms_vals = [x['rms_mean'] for x in p100 if x['rms_mean'] > 0]
if rms_vals:
    import statistics
    mean_rms = statistics.mean(rms_vals)
    stdev_rms = statistics.stdev(rms_vals)
    min_rms = min(rms_vals)
    max_rms = max(rms_vals)
    print(f'  count={len(rms_vals)}, mean={mean_rms:.5f}, stdev={stdev_rms:.5f}, min={min_rms:.5f}, max={max_rms:.5f}')
    # 평균 대비 40% 이하인 구간
    drops = [p100[i] for i, v in enumerate(rms_vals) if v < mean_rms * 0.4]
    print(f'  mean 40% 이하 구간 수: {len(drops)}')
    print(f'  mean 20% 이하 구간 수: {len([v for v in rms_vals if v < mean_rms * 0.2])}')

# segment_features에서 고역 에너지 분포
print()
print('=== SEGMENT FEATURES (고역 에너지 분포) ===')
seg = d['segment_features']
for s in seg[:15]:
    bd = s.get('band_energy_db', {})
    low = bd.get('80_250', 0)
    h2k5 = bd.get('2500_4000', 0)
    h6k = bd.get('6000_10000', 0)
    centroid = s.get('spectral_centroid_mean_hz', 0)
    f0 = s.get('f0_mean_hz', 0)
    rms = s.get('rms_mean', 0)
    print(f"  {s['start_sec']:.1f}~{s['end_sec']:.1f}s | rms={rms:.4f} | f0={f0:.1f}Hz | centroid={centroid:.0f}Hz | 80-250={low:.1f}dB | 2500-4k={h2k5:.1f}dB | 6k-10k={h6k:.1f}dB")

print()
print('=== 전체 세그먼트 고역 에너지 통계 ===')
h2k5_vals = [s.get('band_energy_db', {}).get('2500_4000', 0) for s in seg]
h6k_vals = [s.get('band_energy_db', {}).get('6000_10000', 0) for s in seg]
low_vals = [s.get('band_energy_db', {}).get('80_250', 0) for s in seg]
import statistics
print(f'  2500-4000Hz: mean={statistics.mean(h2k5_vals):.2f}, min={min(h2k5_vals):.2f}, max={max(h2k5_vals):.2f}')
print(f'  6000-10000Hz: mean={statistics.mean(h6k_vals):.2f}, min={min(h6k_vals):.2f}, max={max(h6k_vals):.2f}')
print(f'  80-250Hz: mean={statistics.mean(low_vals):.2f}, min={min(low_vals):.2f}, max={max(low_vals):.2f}')
print(f'  저역-고역 차이(80-250 vs 2500-4000): mean diff={statistics.mean([a-b for a,b in zip(low_vals,h2k5_vals)]):.2f}dB')

# 에코 관련
print()
print('=== ECHO / REVERB 분석 ===')
qr = d['quality_report']
echo_level = qr.get('echo_level', '?')
confidence = qr.get('analysis_confidence', 0)
low_mid_change = qr.get('low_mid_change_db', 0)
method = qr.get('denoise_method', '?')
warning = qr.get('warning', '')
cand = qr.get('candidate_scores', [])
print(f'  echo_level: {echo_level}')
print(f'  analysis_confidence: {confidence}')
print(f'  low_mid_change_db: {low_mid_change:.2f} dB')
print(f'  denoise_method: {method}')
print(f'  warning: {warning}')
print(f'  candidate_scores: {cand}')

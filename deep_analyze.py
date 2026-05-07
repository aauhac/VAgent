import librosa, numpy as np, json

proc = r'c:\VocalAgent\outputs\거의동116_feedback_20260507_012327\processed.wav'
orig_voc = r'c:\VocalAgent\outputs\거의동116_feedback_20260507_012327\demucs\vocals.wav'
converted = r'c:\VocalAgent\outputs\거의동116_feedback_20260507_012327\input_converted.wav'

print('파일 로딩 중...')
y_proc, sr = librosa.load(proc, sr=None, mono=True)
y_orig, _  = librosa.load(orig_voc, sr=None, mono=True)
y_conv, _  = librosa.load(converted, sr=None, mono=True)

print(f'sr={sr}, proc_len={len(y_proc)/sr:.2f}s, voc_len={len(y_orig)/sr:.2f}s, conv_len={len(y_conv)/sr:.2f}s')

min_len = min(len(y_proc), len(y_orig))
y_proc = y_proc[:min_len]
y_orig = y_orig[:min_len]

def band_energy_ratio(y, sr, lo, hi):
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    mask = (freqs >= lo) & (freqs <= hi)
    band = S[mask, :]
    total = S
    ratio = np.mean(np.sum(band**2, axis=0)) / (np.mean(np.sum(total**2, axis=0)) + 1e-12)
    return ratio

def band_energy_db_abs(y, sr, lo, hi):
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    mask = (freqs >= lo) & (freqs <= hi)
    band = S[mask, :]
    e = np.mean(np.sum(band**2, axis=0))
    return 10 * np.log10(e + 1e-12)

print()
print('=== 대역별 에너지 비율 비교 ===')
print(f'{"대역":20s} | {"원본(원래)":>12} | {"Demucs 후":>10} | {"처리 후":>10} | {"Demucs변화":>12} | {"처리변화":>10}')
bands = [
    (80,250,'저역(80-250Hz)'),
    (250,800,'중저역(250-800Hz)'),
    (800,2500,'중역(800-2500Hz)'),
    (2500,5000,'고역(2500-5000Hz)'),
    (5000,10000,'초고역(5-10kHz)'),
    (10000,20000,'공기감(10kHz+)'),
]
for lo, hi, name in bands:
    min3 = min(len(y_conv), len(y_orig), len(y_proc))
    ec = band_energy_db_abs(y_conv[:min3], sr, lo, hi)
    ev = band_energy_db_abs(y_orig[:min3], sr, lo, hi)
    ep = band_energy_db_abs(y_proc[:min3], sr, lo, hi)
    print(f'  {name:22s}| {ec:>10.2f}dB | {ev:>8.2f}dB | {ep:>8.2f}dB | {ev-ec:>+10.2f}dB | {ep-ev:>+8.2f}dB')

print()
print('=== 전체 RMS 비교 ===')
rms_c = np.sqrt(np.mean(y_conv[:min_len]**2))
rms_v = np.sqrt(np.mean(y_orig**2))
rms_p = np.sqrt(np.mean(y_proc**2))
print(f'  원본: {rms_c:.5f}')
print(f'  Demucs 보컬: {rms_v:.5f} ({20*np.log10(rms_v/rms_c+1e-12):+.2f}dB)')
print(f'  최종 처리: {rms_p:.5f} ({20*np.log10(rms_p/rms_v+1e-12):+.2f}dB)')

print()
print('=== 구간별 RMS - 고음/볼륨드롭 구간 탐색 ===')
# 고음 구간과 볼륨 드롭 구간 찾기
hop = int(0.5 * sr)  # 0.5초 단위
n_frames = min_len // hop
print(f'총 {n_frames} 프레임 (0.5초 단위)')

# spectral centroid per 0.5s (고음 여부)
low_volume_high_pitch = []
big_drop = []

prev_rms_p = None
for i in range(n_frames):
    s = i * hop
    e = s + hop
    seg_p = y_proc[s:e]
    seg_v = y_orig[s:e]

    rms_p = np.sqrt(np.mean(seg_p**2))
    rms_v = np.sqrt(np.mean(seg_v**2))

    # spectral centroid (고음 지표)
    if rms_p > 0.005:
        sc = librosa.feature.spectral_centroid(y=seg_p, sr=sr, n_fft=1024, hop_length=256)[0]
        centroid = np.mean(sc)
    else:
        centroid = 0

    t = i * 0.5
    # 고음 구간(centroid > 3000Hz)인데 볼륨이 작은 경우
    if centroid > 3000 and rms_p < 0.04:
        low_volume_high_pitch.append((t, rms_p, rms_v, centroid))

    # 볼륨 급감 (전 구간 대비 50% 이하로 떨어진 경우)
    if prev_rms_p is not None and prev_rms_p > 0.02 and rms_p < prev_rms_p * 0.4:
        big_drop.append((t, prev_rms_p, rms_p, rms_p/prev_rms_p))
    prev_rms_p = rms_p if rms_p > 0.005 else prev_rms_p

print()
print('=== 고음 구간인데 볼륨 작은 구간 ===')
for t, rms_p, rms_v, centroid in low_volume_high_pitch[:15]:
    print(f'  {t:.1f}s: rms_processed={rms_p:.5f}, rms_demucs={rms_v:.5f}, centroid={centroid:.0f}Hz')

print()
print('=== 급격한 볼륨 드롭 구간 (processed.wav 기준) ===')
for t, prev, cur, ratio in big_drop[:15]:
    print(f'  {t:.1f}s: {prev:.5f} → {cur:.5f} (ratio={ratio:.3f})')

# Demucs 에코 잔향 분석: 무음구간(원본이 조용한 구간)에서 processed에 신호가 남아있나?
print()
print('=== 에코 잔향 분석: 무음구간에서 잔신호 여부 ===')
# 원본에서 rms가 낮은 구간 찾기
conv_min = min(len(y_conv), len(y_orig))
hop2 = int(0.1 * sr)
n2 = conv_min // hop2
reverb_detected = []
for i in range(n2 - 3):
    s = i * hop2
    e = s + hop2
    rms_conv = np.sqrt(np.mean(y_conv[s:e]**2))  # 원본
    rms_proc = np.sqrt(np.mean(y_proc[s:e]**2))  # 처리된 보컬
    t = i * 0.1
    # 원본이 조용하고 (rms < 0.005), 처리된 보컬에 신호가 있으면 에코/잔향
    if rms_conv < 0.005 and rms_proc > 0.002:
        reverb_detected.append((t, rms_conv, rms_proc))

print(f'  원본 무음구간에서 보컬 신호가 잔류하는 구간 수: {len(reverb_detected)}')
for t, rc, rp in reverb_detected[:20]:
    print(f'  {t:.2f}s: orig_rms={rc:.6f}, processed_rms={rp:.6f}')

# pitch instability 분석: voiced_ratio와 무음 구간 f0 추적 오류
print()
print('=== pYIN pitch 추적 오류 분석 ===')
with open(r'c:\VocalAgent\outputs\거의동116_feedback_20260507_012327\analysis.json', encoding='utf-8') as f:
    d = json.load(f)

# 무음 구간에서 f0가 추적된 사례
p100 = d['waveform_features']['per_100ms_summary']
pitch_events = [e for e in d['issue_events'] if e['type'] == 'unstable_pitch']

# unstable_pitch 이벤트에서 실제 waveform rms 확인
print(f'  총 unstable_pitch 이벤트: {len(pitch_events)}')
low_rms_pitch = 0
for pe in pitch_events:
    # 해당 구간의 100ms rms 평균
    start, end = pe['start'], pe['end']
    relevant = [p for p in p100 if p['start'] >= start and p['end'] <= end]
    if relevant:
        avg_rms = sum(p['rms_mean'] for p in relevant) / len(relevant)
        if avg_rms < 0.01:  # 거의 무음인데 pitch 불안정으로 감지됨
            low_rms_pitch += 1

print(f'  무음에 가까운 구간(rms<0.01)에서 pitch_unstable 이벤트: {low_rms_pitch}개')
print(f'  → pitch_stability_cents({d["pitch_features"]["pitch_stability_cents"]:.2f}cents)의 일부가 실제 발성이 아닌 무음 구간 노이즈 추적일 가능성')

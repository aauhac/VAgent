"""
vocal_enhancer.py
-----------------
보컬 분리 전·후 오디오 정리 파이프라인.

Demucs 전: 가벼운 전처리 (DC 제거, 약한 HPF, 피크 보호)
           — Demucs 분리 품질을 해치지 않는 범위

Demucs 후: 보컬 stem 처리를 "분석용"과 "청취용"으로 분리

  vocal_analysis  = prepare_vocal_for_analysis()
    - 음색을 크게 바꾸지 않는 약한 처리만 수행
    - 동적 저중역 EQ, 잔향 꼬리 gate
    - F0·RMS·band energy 계산에 사용

  vocal_preview   = prepare_vocal_for_preview()
    - 사람이 들을 때 자연스럽게 들리도록 보정
    - 고역 보상 high shelf + 약한 컴프레서 + 리미터 적용
    - 분석에는 사용하지 않음 (enhancement_report에 설정 기록)
"""

import numpy as np
import librosa
from scipy import signal


# ---------------------------------------------------------------------------
# Demucs 전 전처리
# ---------------------------------------------------------------------------

def preprocess_for_separation(y: np.ndarray, sr: int, low_cut_hz: float = 70.0) -> np.ndarray:
    """
    Demucs 에 넘기기 전 최소한의 전처리.

    수행 내용
    - DC offset 제거
    - 70Hz 하이패스 (zero-phase sosfiltfilt)
    - 피크 보호 (0.98 이하로 제한)
    """
    # DC offset
    y = y - float(np.mean(y))

    # 약한 하이패스 (zero-phase)
    nyq = sr * 0.5
    if low_cut_hz < nyq:
        sos = signal.butter(2, low_cut_hz / nyq, btype="highpass", output="sos")
        y = signal.sosfiltfilt(sos, y)

    # 피크 보호
    peak = float(np.max(np.abs(y))) + 1e-9
    if peak > 0.99:
        y = y / peak * 0.98

    return y.astype(np.float32)


# ---------------------------------------------------------------------------
# Demucs 후 보컬 stem 처리 — 메인 진입점
# ---------------------------------------------------------------------------

def enhance_vocal_stem(y_raw: np.ndarray, sr: int) -> tuple[np.ndarray, dict]:
    """
    분석용 보컬을 생성하고 quality_report를 반환한다.

    내부적으로 여러 후보를 생성해 점수 기반으로 최적 분석용 후보를 선택.

    Returns
    -------
    (y_analysis, quality_report)
      y_analysis   : 분석용 보컬 (음색 최소 변경)
      quality_report : echo_level, 신뢰도, 후보 점수 등
    """
    candidates = {
        "raw":       y_raw,
        "mild_dsp":  _mild_dereverb_and_dynamic_eq(y_raw, sr),
        "tail_gate": _reduce_reverb_tail(y_raw, sr),
    }

    best_name, best_y, candidate_scores = _select_best_candidate(candidates, sr)
    quality_report = _compute_quality_report(
        y_raw, best_y, sr, best_name, candidate_scores
    )
    return best_y, quality_report


def prepare_vocal_for_analysis(y_raw: np.ndarray, sr: int) -> np.ndarray:
    """
    분석용 보컬 생성 (enhance_vocal_stem의 단계별 호출 버전).

    음색을 크게 바꾸지 않는 약한 처리만 수행.
    """
    y, _ = enhance_vocal_stem(y_raw, sr)
    return y


def prepare_vocal_for_preview(
    y_analysis: np.ndarray,
    sr: int,
    high_shelf_freq: int = 3500,
    high_shelf_gain_db: float = 4.0,
    air_shelf_freq: int = 8000,
    air_shelf_gain_db: float = 2.0,
) -> tuple[np.ndarray, dict]:
    """
    청취용 보컬 생성. 분석용 보컬에 고역 보상 + 컴프레서 + 리미터 적용.

    Demucs로 인해 손실된 2.5kHz 이상 고역을 부분 복원하고
    볼륨 편차를 컴프레서로 완화한다.

    Returns
    -------
    (y_preview, enhancement_report)
    """
    y = y_analysis.copy()

    # 1. 고역 보상 high shelf (3.5kHz, +4dB)
    y = _high_shelf(y, sr, freq_hz=high_shelf_freq, gain_db=high_shelf_gain_db, Q=0.7)

    # 2. 공기감 shelf (8kHz, +2dB)
    y = _high_shelf(y, sr, freq_hz=air_shelf_freq, gain_db=air_shelf_gain_db, Q=0.9)

    # 3. 약한 컴프레서 (볼륨 편차 완화)
    y = _light_compressor(
        y, sr,
        threshold_db=-24.0,
        ratio=2.0,
        attack_ms=10.0,
        release_ms=120.0,
    )

    # 4. 리미터 (클리핑 방지)
    y = _limiter(y, ceiling=0.98)

    enhancement_report = {
        "high_shelf_applied": True,
        "high_shelf_freq_hz": high_shelf_freq,
        "high_shelf_gain_db": high_shelf_gain_db,
        "air_shelf_freq_hz": air_shelf_freq,
        "air_shelf_gain_db": air_shelf_gain_db,
        "compressor_threshold_db": -24.0,
        "compressor_ratio": 2.0,
        "limiter_ceiling": 0.98,
        "used_for_analysis": False,
        "used_for_preview": True,
    }
    return y.astype(np.float32), enhancement_report


# ---------------------------------------------------------------------------
# 내부 후보 1: 잔향 tail 기반 스펙트럼 감산 + 동적 EQ
# ---------------------------------------------------------------------------

def _mild_dereverb_and_dynamic_eq(y: np.ndarray, sr: int) -> np.ndarray:
    """
    - 조용한 구간(RMS 하위 25%)을 reverb profile로 추정
    - 보컬 전체가 아닌 reverb profile 수준만 감산 (보컬 손상 최소화)
    - 저중역 과부하 대역만 동적으로 감쇠
    """
    n_fft = 2048
    hop = 512

    stft = librosa.stft(y, n_fft=n_fft, hop_length=hop)
    mag = np.abs(stft)
    phase = np.exp(1j * np.angle(stft))

    # 조용한 프레임 = reverb tail 가능성
    frame_rms = np.sqrt(np.mean(mag ** 2, axis=0))
    threshold = np.percentile(frame_rms, 25)
    quiet_mask = frame_rms < threshold

    if quiet_mask.sum() > 5:
        reverb_profile = np.percentile(mag[:, quiet_mask], 70, axis=1, keepdims=True)
    else:
        reverb_profile = np.percentile(mag, 15, axis=1, keepdims=True)

    # 약하게 감산 (보컬 구간 손상 방지: 최소 10% 유지)
    mag_clean = np.maximum(mag - reverb_profile * 0.6, mag * 0.1)
    y_dereverb = librosa.istft(mag_clean * phase, hop_length=hop, length=len(y))

    # 동적 EQ
    y_clean = _dynamic_low_mid_eq(y_dereverb, sr)

    # 원본 레벨 기준 정규화
    peak_raw = float(np.max(np.abs(y))) + 1e-9
    peak_clean = float(np.max(np.abs(y_clean))) + 1e-9
    if peak_clean > 1e-6:
        y_clean = y_clean / peak_clean * min(peak_raw, 0.98)

    return y_clean.astype(np.float32)


def _dynamic_low_mid_eq(y: np.ndarray, sr: int) -> np.ndarray:
    """
    저중역 대역별 에너지가 해당 대역의 시간축 중앙값보다 +2.5dB 이상 높을 때만 감쇠.

    프레임 단위로 동적 적용 — 특정 순간 부밍 구간만 처리.
    최대 감소량: -4.5dB (= 0.596배)

    대역 기준:
        120~180Hz : 룸 저역 울림
        180~280Hz : 먹먹함 / 저중역 부밍
        280~450Hz : 답답함
        450~700Hz : 박스감
    """
    n_fft = 2048
    hop = 512

    stft = librosa.stft(y, n_fft=n_fft, hop_length=hop)
    mag = np.abs(stft)
    phase = np.exp(1j * np.angle(stft))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    mag_eq = mag.copy()

    # (대역 Hz 범위, 최대 감쇠비) — 0.60 ≈ -4.5dB
    bands = [
        (120, 180, 0.60),   # 룸 저역 울림
        (180, 280, 0.60),   # 먹먹함
        (280, 450, 0.70),   # 답답함
        (450, 700, 0.80),   # 박스감 — 약하게
    ]

    for low, high, max_attenuation in bands:
        mask = (freqs >= low) & (freqs < high)
        if not mask.any():
            continue

        band_energy_per_frame = np.mean(mag[mask, :] ** 2, axis=0)  # (frames,)
        median_energy = float(np.median(band_energy_per_frame)) + 1e-20

        # threshold: 중앙값 대비 +2.5dB 이상이면 약하게 감소
        #            +5.0dB 이상이면 강하게 감소
        thresh_mild   = median_energy * (10 ** (2.5 / 10))  # ×1.778
        thresh_strong = median_energy * (10 ** (5.0 / 10))  # ×3.162

        attenuation_mild = 1.0 - (1.0 - max_attenuation) * 0.45

        gain = np.ones(mag.shape[1], dtype=np.float32)
        gain[band_energy_per_frame > thresh_mild]   = attenuation_mild
        gain[band_energy_per_frame > thresh_strong] = max_attenuation

        mag_eq[mask, :] *= gain[np.newaxis, :]

    y_eq = librosa.istft(mag_eq * phase, hop_length=hop, length=len(y))
    return y_eq.astype(np.float32)


# ---------------------------------------------------------------------------
# 내부 후보 2: F0/RMS 기반 구절 끝 tail gate
# ---------------------------------------------------------------------------

def _reduce_reverb_tail(y: np.ndarray, sr: int) -> np.ndarray:
    """
    보컬 활성 구간 직후 남는 잔향 꼬리에만 gain을 줄인다.

    로직:
    - RMS > threshold → vocal active
    - vocal active 종료 후 300ms: natural fade (0.5까지)
    - 300ms 초과 조용한 구간: 추가 감쇠 (0.25)
    """
    hop = int(sr * 0.05)  # 50ms 프레임
    frame_rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    n_frames = len(frame_rms)

    rms_mean = float(np.mean(frame_rms))
    rms_threshold = rms_mean * 0.30

    max_tail_frames = int(0.3 * sr / hop)  # 300ms

    gain = np.ones(n_frames, dtype=np.float32)
    was_vocal = False
    tail_frames = 0

    for i, rms in enumerate(frame_rms):
        is_vocal = rms > rms_threshold
        if is_vocal:
            was_vocal = True
            tail_frames = 0
            gain[i] = 1.0
        elif was_vocal:
            tail_frames += 1
            if tail_frames <= max_tail_frames:
                gain[i] = max(1.0 - (tail_frames / max_tail_frames) * 0.5, 0.5)
            else:
                gain[i] = 0.25
                was_vocal = False

    # frame → sample 보간
    frame_samples = librosa.frames_to_samples(np.arange(n_frames), hop_length=hop)
    gain_samples = np.interp(
        np.arange(len(y)), frame_samples, gain
    ).astype(np.float32)

    return (y * gain_samples).astype(np.float32)


# ---------------------------------------------------------------------------
# 고역 보상 / 컴프레서 / 리미터 (청취용 전용)
# ---------------------------------------------------------------------------

def _high_shelf(y: np.ndarray, sr: int, freq_hz: float, gain_db: float, Q: float = 0.7) -> np.ndarray:
    """Biquad high shelf filter (zero-phase sosfiltfilt)."""
    w0 = 2.0 * np.pi * freq_hz / sr
    A = 10.0 ** (gain_db / 40.0)
    alpha = np.sin(w0) / 2.0 * np.sqrt((A + 1.0 / A) * (1.0 / Q - 1.0) + 2.0)

    b0 =      A * ((A + 1) + (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha)
    b1 = -2 * A * ((A - 1) + (A + 1) * np.cos(w0))
    b2 =      A * ((A + 1) + (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha)
    a0 =           (A + 1) - (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha
    a1 =      2 * ((A - 1) - (A + 1) * np.cos(w0))
    a2 =           (A + 1) - (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha

    sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
    return signal.sosfiltfilt(sos, y).astype(np.float32)


def _light_compressor(
    y: np.ndarray,
    sr: int,
    threshold_db: float = -24.0,
    ratio: float = 2.0,
    attack_ms: float = 10.0,
    release_ms: float = 120.0,
) -> np.ndarray:
    """
    샘플 단위 피크 컴프레서.
    - threshold 초과 시 ratio:1 압축
    - attack/release 시정수로 부드럽게 적용
    """
    threshold_lin = 10.0 ** (threshold_db / 20.0)
    attack_coef   = np.exp(-1.0 / (sr * attack_ms  / 1000.0))
    release_coef  = np.exp(-1.0 / (sr * release_ms / 1000.0))

    out = np.zeros_like(y)
    gain = 1.0
    for i, sample in enumerate(np.abs(y)):
        if sample > threshold_lin:
            # threshold 초과: 압축 gain 계산
            target_gain = (threshold_lin * (sample / threshold_lin) ** (1.0 / ratio)) / (sample + 1e-12)
        else:
            target_gain = 1.0

        if target_gain < gain:
            gain = attack_coef * gain + (1.0 - attack_coef) * target_gain
        else:
            gain = release_coef * gain + (1.0 - release_coef) * target_gain
        out[i] = y[i] * gain

    return out.astype(np.float32)


def _limiter(y: np.ndarray, ceiling: float = 0.98) -> np.ndarray:
    """단순 피크 리미터 (클리핑 방지)."""
    peak = float(np.max(np.abs(y))) + 1e-9
    if peak > ceiling:
        y = y / peak * ceiling
    return y.astype(np.float32)


# ---------------------------------------------------------------------------
# 후보 선택
# ---------------------------------------------------------------------------

def _select_best_candidate(
    candidates: dict,
    sr: int,
) -> tuple[str, np.ndarray, dict]:
    """
    저중역 감소량, 고역 보존, artifact penalty 기준으로 최적 후보 선택.
    """
    all_scores: dict[str, dict] = {}
    best_name = "raw"
    best_score = -999.0

    for name, y_cand in candidates.items():
        s = _score_candidate(candidates["raw"], y_cand, sr)
        all_scores[name] = s
        if s["final_score"] > best_score:
            best_score = s["final_score"]
            best_name = name

    return best_name, candidates[best_name], all_scores


def _score_candidate(y_raw: np.ndarray, y_cand: np.ndarray, sr: int) -> dict:
    """
    개별 후보 점수 계산.

    점수 구성:
    - low_mid_reduction  (0~1)  : 저중역 비율 감소 → 높을수록 좋음  (×0.35)
    - air_preservation   (0~1)  : 6~10kHz 보존 → 높을수록 좋음      (×0.30)
    - artifact_penalty   (0~1)  : spectral flatness 급변 → 낮을수록  (×0.35, 차감)
    """
    hop = 512
    n_fft = 2048
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    mag_r = np.abs(librosa.stft(y_raw,  n_fft=n_fft, hop_length=hop))
    mag_c = np.abs(librosa.stft(y_cand, n_fft=n_fft, hop_length=hop))

    low_mid_mask = (freqs >= 120) & (freqs < 700)
    high_mask    = freqs >= 2000
    air_mask     = (freqs >= 6000) & (freqs < 10000)

    def low_to_high_ratio(mag):
        lo = float(np.mean(mag[low_mid_mask, :])) + 1e-10
        hi = float(np.mean(mag[high_mask,    :])) + 1e-10
        return lo / hi

    raw_ratio  = low_to_high_ratio(mag_r)
    cand_ratio = low_to_high_ratio(mag_c)
    low_mid_reduction = max(0.0, min(1.0, (raw_ratio - cand_ratio) / (raw_ratio + 1e-10)))

    air_raw  = float(np.mean(mag_r[air_mask, :])) + 1e-10
    air_cand = float(np.mean(mag_c[air_mask, :])) + 1e-10
    air_preservation = min(1.0, air_cand / air_raw)

    flat_r = float(np.mean(librosa.feature.spectral_flatness(y=y_raw)))
    flat_c = float(np.mean(librosa.feature.spectral_flatness(y=y_cand)))
    artifact_penalty = max(0.0, (flat_c - flat_r) / (flat_r + 1e-10))

    final_score = (
        0.35 * low_mid_reduction
        + 0.30 * air_preservation
        - 0.35 * min(artifact_penalty, 1.0)
    )

    return {
        "low_mid_reduction": round(low_mid_reduction, 3),
        "air_preservation":  round(air_preservation,  3),
        "artifact_penalty":  round(artifact_penalty,  3),
        "final_score":       round(final_score,       3),
    }


# ---------------------------------------------------------------------------
# 품질 리포트 생성
# ---------------------------------------------------------------------------

def _compute_quality_report(
    y_raw: np.ndarray,
    y_clean: np.ndarray,
    sr: int,
    method_used: str,
    candidate_scores: dict,
) -> dict:
    """
    analysis.json / LLM 에 포함할 quality_report 생성.

    항목:
    - echo_level            : high / medium / low
    - low_mid_change_db     : 전처리로 저중역이 변한 dB
    - denoise_method        : 선택된 후보명
    - analysis_confidence   : 0~1 (분석 신뢰도 추정)
    - candidate_scores      : 각 후보 점수
    - warning               : LLM에 전달할 경고문 (None 가능)
    """
    hop = 512
    n_fft = 2048
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    stft_r = np.abs(librosa.stft(y_raw,   n_fft=n_fft, hop_length=hop))
    stft_c = np.abs(librosa.stft(y_clean, n_fft=n_fft, hop_length=hop))

    low_mid_mask = (freqs >= 120) & (freqs < 700)

    def band_db(s, mask):
        e = float(np.mean(s[mask, :])) + 1e-10
        return round(10 * np.log10(e), 2)

    raw_low_db   = band_db(stft_r, low_mid_mask)
    clean_low_db = band_db(stft_c, low_mid_mask)
    low_mid_change_db = round(clean_low_db - raw_low_db, 2)

    # 에코 레벨: 조용한 구간(하위 10%) / 활성 구간(상위 50%) 에너지 비율
    frame_rms = librosa.feature.rms(y=y_raw, hop_length=hop)[0]
    rms_sorted = np.sort(frame_rms)
    n = len(rms_sorted)
    quiet_energy  = float(np.mean(rms_sorted[:max(1, n // 10)]))
    active_energy = float(np.mean(rms_sorted[n // 2:])) + 1e-10
    echo_ratio = quiet_energy / active_energy

    if echo_ratio > 0.30:
        echo_level   = "high"
        confidence   = 0.55
        warning = (
            "잔향이 강해 저중역(120~500Hz)이 실제 보컬보다 높게 측정되었을 수 있습니다. "
            "저중역 관련 피드백은 발성 문제뿐 아니라 녹음 환경 영향도 함께 고려하세요."
        )
    elif echo_ratio > 0.15:
        echo_level   = "medium"
        confidence   = 0.75
        warning = "약간의 잔향이 있어 저중역 분석에 영향이 있을 수 있습니다."
    else:
        echo_level   = "low"
        confidence   = 0.90
        warning = None

    return {
        "echo_level":          echo_level,
        "low_mid_change_db":   low_mid_change_db,
        "denoise_method":      method_used,
        "analysis_confidence": confidence,
        "candidate_scores":    candidate_scores,
        "warning":             warning,
    }



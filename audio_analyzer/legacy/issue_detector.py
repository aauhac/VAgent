"""
issue_detector.py
-----------------
분석 피처를 규칙 기반으로 해석해 이슈 레이블 목록을 반환한다.

반환 레이블 목록 (중복 가능)
    low_mid_heavy      : 80~250Hz 과다 → 둔탁함, 목 누름 가능성
    boxy_resonance     : 500~800Hz 과다 → 박스감, 소리 뒤로 먹는 느낌
    presence_weak      : 2500~4000Hz 부족 → 전방 선명도 약함
    airiness_weak      : 6000~10000Hz 부족 → 공기감/개방감 부족
    pitch_unstable     : pitch_stability_cents 높음 → 음을 흔들림 없이 유지 못함
    pitch_low_voiced   : voiced_ratio 낮음 → 실제 유성음 구간이 적음
    low_dynamics       : dynamic_range_db 낮음 → 강약 조절이 적음

판단 기준은 각 대역 에너지의 평균 대비 z-score 와
pitch stability 절댓값 임계치로 결정한다.
"""

import numpy as np


# 임계치 상수
_BAND_Z_HIGH = 0.6    # z-score 이상이면 "과다"
_BAND_Z_LOW = -0.6   # z-score 이하이면 "부족"
_PITCH_STABLE_CENTS = 50.0   # cents 이상이면 불안정
_VOICED_RATIO_LOW = 0.55     # 유성음 비율 임계치
_DYNAMIC_RANGE_LOW = 6.0     # dB 이하이면 강약이 단조로움


def detect_issue_events(
    pitch_features: dict,
    segment_features: list,
    waveform_features: dict,
) -> list[dict]:
    """
    프레임/구간 데이터를 기반으로 문제가 발생한 시간 구간을 특정해 반환한다.

    반환 형태:
    [
      {
        "type": "unstable_pitch",
        "start": 12.4,
        "end": 13.8,
        "severity": "high",
        "detail": {...},
        "description": "..."
      },
      ...
    ]
    """
    events: list[dict] = []

    # ── 1. 구간별 pitch 불안정 구간 감지 ──────────────────────────────────────
    frame_f0 = pitch_features.get("frame_f0", [])
    if frame_f0:
        ref_hz = pitch_features.get("f0_mean_hz") or 300.0
        # 0.5초 슬라이딩 윈도우로 불안정 구간 검출
        window = []
        for entry in frame_f0:
            t = entry["time_sec"]
            hz = entry["f0_hz"]
            if hz is None:
                continue
            window.append((t, hz))

        # 연속된 불안정 프레임 묶기 (cents 편차가 100 이상인 구간)
        unstable_start = None
        unstable_frames = []
        for t, hz in window:
            cents_dev = abs(1200 * np.log2(hz / ref_hz + 1e-10))
            if cents_dev > 100:
                if unstable_start is None:
                    unstable_start = t
                unstable_frames.append((t, hz, cents_dev))
            else:
                if unstable_start is not None and len(unstable_frames) >= 3:
                    avg_dev = float(np.mean([f[2] for f in unstable_frames]))
                    events.append({
                        "type": "unstable_pitch",
                        "start": round(unstable_start, 2),
                        "end": round(unstable_frames[-1][0], 2),
                        "severity": "high" if avg_dev > 200 else "medium",
                        "detail": {
                            "avg_deviation_cents": round(avg_dev, 1),
                            "reference_hz": round(ref_hz, 1),
                        },
                        "description": f"음정이 기준(±1semitone)을 벗어나 흔들림 (평균 {round(avg_dev)}cents 편차)",
                    })
                unstable_start = None
                unstable_frames = []

    # ── 2. 구간별 음량 급락 감지 ───────────────────────────────────────────────
    per_100ms = waveform_features.get("per_100ms_summary", [])
    if len(per_100ms) >= 3:
        rms_vals = [e["rms_mean"] for e in per_100ms]
        mean_rms = float(np.mean(rms_vals))
        for i in range(1, len(per_100ms) - 1):
            prev = per_100ms[i - 1]["rms_mean"]
            curr = per_100ms[i]["rms_mean"]
            if prev > mean_rms * 0.5 and curr < prev * 0.4:
                ratio = float(curr / (prev + 1e-10))
                drop_db = round(20 * np.log10(ratio + 1e-10), 1)
                events.append({
                    "type": "volume_drop",
                    "start": per_100ms[i]["start"],
                    "end": per_100ms[i]["end"],
                    "severity": "high" if drop_db < -10 else "medium",
                    "detail": {
                        "rms_before": round(float(prev), 6),
                        "rms_after": round(float(curr), 6),
                        "ratio": round(ratio, 3),
                        "rms_drop_db": drop_db,
                    },
                    "description": (
                        f"음량이 {abs(drop_db):.1f}dB 급락 "
                        f"(직전 {prev:.4f} → {curr:.4f} RMS, {ratio:.2f}배) "
                        f"— 끝음 처리 또는 고음 진입 시 힘 빠짐 가능"
                    ),
                })

    # ── 3. 구간별 주파수 불균형 감지 ───────────────────────────────────────────
    for seg in segment_features:
        band = seg.get("band_energy_db", {})
        low = band.get("80_250", 0)
        presence = band.get("2500_4000", 0)
        high = band.get("6000_10000", 0)
        if low - presence > 20:
            events.append({
                "type": "low_mid_heavy",
                "start": seg["start_sec"],
                "end": seg["end_sec"],
                "severity": "medium",
                "detail": {
                    "low_band_db": round(low, 1),
                    "presence_band_db": round(presence, 1),
                    "gap_db": round(low - presence, 1),
                },
                "description": f"{seg['start_sec']:.0f}~{seg['end_sec']:.0f}초 구간 저중역({round(low,1)}dB)이 존재감 대역({round(presence,1)}dB)보다 {round(low-presence,1)}dB 높음",
            })

    return events


def detect_issues(
    frequency_features: dict,
    pitch_features: dict,
    timbre_features: dict,
) -> list[str]:
    """이슈 레이블 목록을 반환한다."""

    issues: list[str] = []
    band = frequency_features["band_energy_db"]

    # 대역별 z-score 계산
    energies = np.array(list(band.values()))
    mean_e = float(np.mean(energies))
    std_e = float(np.std(energies))

    def z(key: str) -> float:
        if std_e < 1e-6:
            return 0.0
        return (band.get(key, mean_e) - mean_e) / std_e

    # 저중역 과다
    if z("80_250") > _BAND_Z_HIGH:
        issues.append("low_mid_heavy")

    # 박스감 과다
    if z("500_800") > _BAND_Z_HIGH:
        issues.append("boxy_resonance")

    # Presence 부족
    if z("2500_4000") < _BAND_Z_LOW:
        issues.append("presence_weak")

    # 공기감 부족
    if z("6000_10000") < _BAND_Z_LOW:
        issues.append("airiness_weak")

    # Pitch 불안정
    stability = pitch_features.get("pitch_stability_cents")
    if stability is not None and stability > _PITCH_STABLE_CENTS:
        issues.append("pitch_unstable")

    # 유성음 비율 낮음
    voiced_ratio = pitch_features.get("voiced_ratio", 1.0)
    if voiced_ratio < _VOICED_RATIO_LOW:
        issues.append("low_voiced_ratio")

    return issues

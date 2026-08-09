"""
artifact_filter.py
------------------
분석 파이프라인(보컬 분리 → denoise → F0 추출)에서 발생하는
Preprocessing Artifact를 감지하고, 이슈를 두 그룹으로 분류한다.

결과:
    feedback_eligible   : LLM에 "개선 포인트"로 전달할 이슈 목록
    artifact_warnings   : 전처리 영향 가능성 → LLM에 "참고사항"으로만 전달
    demucs_hf_loss      : Demucs 고역 손실 감지 여부 (bool)
    artifact_notes      : 사용자 표시용 참고 문장 목록

배경 지식:
- Demucs htdemucs: 2.5kHz 이상 고역에서 8~17dB 손실 흔함
- pYIN: 저볼륨 프레임 / 빠른 전이 구간에서 octave error 발생 가능
- volume_drop: 보컬 stem tail에서 fade artifact가 drop처럼 보임
- low_mid_heavy: 고역이 손실되면 저중역이 상대적으로 높게 측정됨
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 상수 정의
# ---------------------------------------------------------------------------

# 기본적으로 전처리에 민감한 이슈 (artifact_warning 기본 처리)
_PREPROCESSING_SENSITIVE: frozenset[str] = frozenset({
    "volume_drop",
    "pitch_unstable",
    "low_voiced_ratio",
    "low_dynamics",
})

# 요청 반영: 중저역 계열 피드백도 기본 제한
_LOW_MID_SENSITIVE: frozenset[str] = frozenset({
    "low_mid_heavy",
    "boxy_resonance",
})

# Demucs 고역 손실 감지 임계값
# low-mid(80-250Hz) 대비 airiness(6000-10000Hz) 차이가 이 이상이면 고역 손실로 판정
_DEMUCS_HF_LOSS_GAP_DB = 14.0

# 절대값 기준: airiness가 이 이하이면 고역 손실로 판정 (dBFS 기준 상대적 낮음)
# band_energy_db는 log scale이므로 presence보다 airiness가 10dB 이상 낮으면 이상
_DEMUCS_HF_LOSS_PRESENCE_GAP_DB = 10.0

# artifact_warning으로 처리된 이슈들을 위한 사용자 표시 문구
_ARTIFACT_NOTE_TEMPLATES: dict[str, str] = {
    "pitch_unstable": (
        "음정 추적 수치가 일부 구간에서 불안정하게 측정되었습니다. "
        "이는 보컬 분리 과정의 잡음이나 피치 추적 알고리즘의 한계 때문일 수 있으므로, "
        "실제 발성 문제로 단정하기 어렵습니다."
    ),
    "volume_drop": (
        "일부 구간에서 소리 크기가 갑자기 작아지는 패턴이 측정되었습니다. "
        "보컬 분리 후 소리 끝부분에서 자연스럽게 발생하는 현상일 수 있어 "
        "발성 문제로 단정하지 않습니다."
    ),
    "low_voiced_ratio": (
        "분석 가능한 유성음 구간이 예상보다 적게 측정되었습니다. "
        "녹음 볼륨, 반주 세기, 보컬 분리 정확도에 따라 달라질 수 있습니다."
    ),
    "low_dynamics": (
        "강약 변화 수치가 낮게 측정되었습니다. "
        "보컬 분리 후 다이나믹 압축 효과가 생길 수 있어 실제 발성과 차이가 있을 수 있습니다."
    ),
    "presence_weak": (
        "2500~4000Hz 대역이 낮게 측정되었습니다. "
        "보컬 분리 과정에서 이 영역의 손실이 발생할 수 있어 "
        "가사 전달력 문제로 단정하기 어렵습니다."
    ),
    "airiness_weak": (
        "6000~10000Hz 고역 대역이 낮게 측정되었습니다. "
        "보컬 분리 과정에서 고역 손실이 흔히 발생하므로 "
        "끝음 처리 문제로 단정하기 어렵습니다."
    ),
    "low_mid_heavy": (
        "저중역(80~250Hz)이 상대적으로 높게 측정되었습니다. "
        "고역 손실로 인해 저중역이 상대적으로 두드러져 보일 수 있어 "
        "발성의 무게감 문제로 단정하기 어렵습니다."
    ),
    "boxy_resonance": (
        "500~800Hz 대역이 높게 측정되었습니다. "
        "고역 손실이 동반되면 이 대역이 상대적으로 두드러지는 경향이 있어 "
        "공명 문제로 단정하기 어렵습니다."
    ),
}


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------

def filter_preprocessing_artifacts(analysis_result: dict) -> dict:
    """
    analysis_result를 분석하여 이슈를 두 그룹으로 분류한다.

    Parameters
    ----------
    analysis_result : analyze_mp3() 반환 dict

    Returns
    -------
    {
        "feedback_eligible":  [str, ...],   # 실제 개선 포인트로 전달할 이슈
        "artifact_warnings":  [             # 참고사항으로만 전달할 이슈
            {"type": str, "reason": str, "note": str},
            ...
        ],
        "demucs_hf_loss":     bool,         # Demucs 고역 손실 감지 여부
        "artifact_notes":     [str, ...],   # 사용자 표시용 짧은 참고 문장
    }
    """
    issues: list[str] = analysis_result.get("detected_issues", [])
    freq = analysis_result.get("frequency_features", {})
    band = freq.get("band_energy_db", {})

    # ── 1. Demucs 고역 손실 감지 ──────────────────────────────────────────
    demucs_hf_loss = _detect_demucs_hf_loss(band)

    # ── 2. 이슈 분류 ─────────────────────────────────────────────────────
    feedback_eligible: list[str] = []
    artifact_warnings: list[dict] = []

    for issue in issues:
        classification = _classify_issue(issue, band, demucs_hf_loss)
        if classification["eligible"]:
            feedback_eligible.append(issue)
        else:
            artifact_warnings.append({
                "type":   issue,
                "reason": classification["reason"],
                "note":   _ARTIFACT_NOTE_TEMPLATES.get(issue, ""),
            })

    # ── 3. 사용자용 참고 문장 수집 ──────────────────────────────────────
    artifact_notes = [
        _ARTIFACT_NOTE_TEMPLATES[w["type"]]
        for w in artifact_warnings
        if w["type"] in _ARTIFACT_NOTE_TEMPLATES
    ]

    return {
        "feedback_eligible":  feedback_eligible,
        "artifact_warnings":  artifact_warnings,
        "demucs_hf_loss":     demucs_hf_loss,
        "artifact_notes":     artifact_notes,
    }


# ---------------------------------------------------------------------------
# 내부 함수
# ---------------------------------------------------------------------------

def _detect_demucs_hf_loss(band: dict) -> bool:
    """
    주파수 대역 에너지를 보고 Demucs 고역 손실 여부를 판정한다.

    판정 기준 (하나라도 해당하면 True):
    1. low_mid(80-250Hz) - airiness(6000-10000Hz) > 14dB
    2. presence(2500-4000Hz) - airiness(6000-10000Hz) > 10dB
    """
    if not band:
        return False

    low_mid   = band.get("80_250")
    presence  = band.get("2500_4000")
    airiness  = band.get("6000_10000")

    if airiness is None:
        return False

    # 기준 1: 저중역 대비 고역 격차
    if low_mid is not None and (low_mid - airiness) > _DEMUCS_HF_LOSS_GAP_DB:
        return True

    # 기준 2: 존재감 대역 대비 고역 격차
    if presence is not None and (presence - airiness) > _DEMUCS_HF_LOSS_PRESENCE_GAP_DB:
        return True

    return False


def _classify_issue(issue: str, band: dict, demucs_hf_loss: bool) -> dict:
    """
    개별 이슈를 분류한다.

    Returns
    -------
    {"eligible": bool, "reason": str}
    """
    # 항상 전처리 민감 → artifact_warning
    if issue in _PREPROCESSING_SENSITIVE:
        return {
            "eligible": False,
            "reason": "보컬 분리/피치 추적 전처리 과정에서 흔히 발생하는 현상입니다.",
        }

    # 요청 반영: 중저역 계열(low_mid/boxy)은 기본적으로 참고사항 처리
    if issue in _LOW_MID_SENSITIVE:
        return {
            "eligible": False,
            "reason": "중저역 계열 피드백은 전처리/분리 영향이 커서 기본적으로 참고사항으로만 처리합니다.",
        }

    # 고역 손실은 참고 신호로만 유지한다.
    # presence_weak / airiness_weak는 더 이상 일괄 제외하지 않는다.
    if demucs_hf_loss:
        if issue in ("presence_weak", "airiness_weak"):
            return {
                "eligible": True,
                "reason": "",
            }

    # 그 외는 개선 포인트로 전달
    return {"eligible": True, "reason": ""}

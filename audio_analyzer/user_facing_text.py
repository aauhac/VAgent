"""
user_facing_text.py
-------------------
내부 이슈 레이블(low_mid_heavy, boxy_resonance …)과 강점 레이블을
일반 사용자가 읽을 수 있는 보컬 코칭 언어로 변환한다.

내부 레이블은 그대로 유지하고,
사용자에게 보여주는 문장만 이 파일에서 관리한다.
"""

# ---------------------------------------------------------------------------
# 이슈별 사용자 표시 텍스트
# ---------------------------------------------------------------------------

USER_FACING_ISSUE_TEXT: dict[str, dict] = {
    "low_mid_heavy": {
        "display_title": "소리가 아래로 눌려 들림",
        "user_symptom": "목소리가 가볍게 앞으로 나오기보다 아래쪽에 무겁게 머무는 느낌이 있습니다.",
        "possible_cause": "고음으로 갈 때도 낮은 음을 낼 때의 무게를 그대로 가져가고 있을 가능성이 있습니다.",
        "vocal_advice": "소리를 크게 밀기보다, 말하듯 앞쪽으로 가볍게 붙여보세요.",
        "practice": "립트릴로 같은 구간을 먼저 부른 뒤, '니-네-냐' 발음으로 작게 다시 불러보세요.",
    },
    "boxy_resonance": {
        "display_title": "소리가 입 안에서 맴돎",
        "user_symptom": "목소리가 밖으로 시원하게 나오기보다 입 안쪽에 머무는 느낌이 있습니다.",
        "possible_cause": "입을 크게 열려고 하면서 혀나 모음 위치가 뒤로 가고 있을 가능성이 있습니다.",
        "vocal_advice": "턱을 많이 내리기보다, 평소 말할 때처럼 발음을 앞쪽에 두세요.",
        "practice": "'네', '니', '냐'로 같은 멜로디를 부르며 소리가 앞으로 나오는지 확인하세요.",
    },
    "presence_weak": {
        "display_title": "가사와 음의 시작이 덜 또렷함",
        "user_symptom": "목소리가 반주 앞으로 잘 나오지 않고, 가사의 윤곽이 약하게 들릴 수 있습니다.",
        "possible_cause": "소리를 부드럽게 내려고 하면서 음의 시작이나 발음이 흐려졌을 가능성이 있습니다.",
        "vocal_advice": "소리를 세게 지르기보다, 첫 자음을 조금 더 분명하게 말하듯 시작하세요.",
        "practice": "가사를 말하듯 읽은 뒤, 같은 느낌으로 낮은 볼륨에서 멜로디를 붙여보세요.",
    },
    "airiness_weak": {
        "display_title": "소리 끝의 여유가 부족함",
        "user_symptom": "소리 끝이 빨리 닫히거나, 여운이 자연스럽게 남지 않는 느낌이 있을 수 있습니다.",
        "possible_cause": "끝음에서 힘이 빠지거나, 반대로 목을 닫으며 마무리하고 있을 가능성이 있습니다.",
        "vocal_advice": "끝음을 갑자기 끊지 말고, 작은 소리로 부드럽게 정리해보세요.",
        "practice": "'하—', '후—'로 짧게 소리를 낸 뒤 끝을 급하게 닫지 않는 연습을 해보세요.",
    },
    "pitch_unstable": {
        "display_title": "음이 위아래로 흔들림",
        "user_symptom": "한 음을 유지할 때 음높이가 고정되지 않고 흔들리는 구간이 있습니다.",
        "possible_cause": "호흡 압력이나 목 주변 힘 조절이 일정하지 않을 가능성이 있습니다.",
        "vocal_advice": "큰 소리로 버티기보다, 작은 볼륨에서 목표 음을 먼저 안정적으로 유지하세요.",
        "practice": "피아노나 튜너 기준음에 맞춰 3초 동안 같은 음을 유지하는 연습을 하세요.",
    },
    "low_voiced_ratio": {
        "display_title": "목소리로 선명하게 잡힌 구간이 적음",
        "user_symptom": "분석상 실제 목소리로 안정적으로 잡힌 구간이 적습니다.",
        "possible_cause": "배경 소음, 반주, 숨소리, 너무 작은 녹음 볼륨의 영향일 수 있습니다.",
        "vocal_advice": "마이크와의 거리를 일정하게 두고, 반주보다 목소리가 조금 더 크게 녹음되도록 해보세요.",
        "practice": "같은 구간을 반주 없이 한 번 녹음해서 비교해보세요.",
    },
    "low_dynamics": {
        "display_title": "강약 차이가 적음",
        "user_symptom": "구간마다 소리 세기 변화가 적어 노래가 평평하게 들릴 수 있습니다.",
        "possible_cause": "음정을 맞추는 데 집중하면서 문장별 강조가 줄어들었을 가능성이 있습니다.",
        "vocal_advice": "모든 음을 같은 세기로 부르기보다, 중요한 단어만 살짝 더 분명하게 불러보세요.",
        "practice": "한 문장을 말하듯 읽고, 강조되는 단어만 10~20% 더 크게 불러보세요.",
    },
}

# ---------------------------------------------------------------------------
# 강점별 사용자 표시 텍스트 (이슈가 감지되지 않은 항목)
# ---------------------------------------------------------------------------

USER_FACING_STRENGTH_TEXT: dict[str, dict] = {
    "balanced_low_mid": {
        "display_title": "소리의 무게가 과하지 않음",
        "message": "목소리가 아래로 과하게 눌리지 않고 비교적 편하게 유지되고 있습니다.",
        "keep_advice": "지금처럼 고음으로 갈 때 소리를 너무 무겁게 끌고 가지 않는 느낌을 유지하세요.",
    },
    "boxiness_controlled": {
        "display_title": "소리가 입 안에 갇히지 않음",
        "message": "소리가 입 안에서 과하게 맴돌지 않고 비교적 자연스럽게 나오는 편입니다.",
        "keep_advice": "입을 억지로 크게 열기보다, 말하듯 편한 발음 위치를 유지하세요.",
    },
    "presence_adequate": {
        "display_title": "가사와 음의 시작이 비교적 잘 들림",
        "message": "목소리가 반주 뒤로 많이 묻히지 않고, 가사의 윤곽이 어느 정도 유지됩니다.",
        "keep_advice": "첫 자음을 지금처럼 너무 흐리지 않게 시작하는 것이 좋습니다.",
    },
    "airiness_adequate": {
        "display_title": "소리 끝이 너무 답답하지 않음",
        "message": "끝음이 과하게 닫히지 않고 어느 정도 자연스럽게 정리됩니다.",
        "keep_advice": "끝음을 갑자기 끊지 말고 지금처럼 자연스럽게 마무리하세요.",
    },
    "pitch_stable": {
        "display_title": "음정 유지가 비교적 안정적임",
        "message": "한 음을 유지할 때 큰 흔들림이 많지 않습니다.",
        "keep_advice": "큰 소리보다 현재처럼 안정적으로 음을 잡는 감각을 유지하세요.",
    },
    "voiced_ratio_good": {
        "display_title": "목소리 분석 구간이 충분함",
        "message": "분석에 사용할 수 있을 만큼 목소리가 충분히 선명하게 잡혔습니다.",
        "keep_advice": "마이크 거리와 녹음 볼륨을 지금과 비슷하게 유지하면 좋습니다.",
    },
    "dynamics_good": {
        "display_title": "강약 변화가 어느 정도 살아 있음",
        "message": "노래 안에서 소리 세기 변화가 어느 정도 나타나고 있습니다.",
        "keep_advice": "중요한 단어와 감정이 들어가는 부분만 살짝 더 살리는 방향으로 유지하세요.",
    },
}

# 내부 이슈 레이블 → 대응 강점 레이블
_ISSUE_TO_STRENGTH: dict[str, str] = {
    "low_mid_heavy":    "balanced_low_mid",
    "boxy_resonance":   "boxiness_controlled",
    "presence_weak":    "presence_adequate",
    "airiness_weak":    "airiness_adequate",
    "pitch_unstable":   "pitch_stable",
    "low_voiced_ratio": "voiced_ratio_good",
    "low_dynamics":     "dynamics_good",
}

# ---------------------------------------------------------------------------
# 변환 함수
# ---------------------------------------------------------------------------

def to_user_facing_issue(issue_type: str, evidence: dict | None = None) -> dict:
    """
    내부 이슈 레이블을 사용자 표시용 dict로 변환한다.

    Parameters
    ----------
    issue_type : "low_mid_heavy", "boxy_resonance" 등 내부 레이블
    evidence   : LLM에 전달할 기술적 근거 수치 dict (선택)
    """
    template = USER_FACING_ISSUE_TEXT.get(issue_type)
    if not template:
        return {
            "type": issue_type,
            "display_title": "개선이 필요한 구간",
            "user_symptom": "분석 결과상 조정이 필요한 부분이 있습니다.",
            "possible_cause": "녹음 환경이나 발성 습관에서 원인을 찾아볼 수 있습니다.",
            "vocal_advice": "무리해서 소리를 바꾸기보다 작은 볼륨에서 다시 확인해보세요.",
            "practice": "문제 구간을 2~3초 단위로 나누어 반복 녹음해보세요.",
            "technical_evidence": evidence or {},
        }

    return {
        "type": issue_type,
        "display_title": template["display_title"],
        "user_symptom": template["user_symptom"],
        "possible_cause": template["possible_cause"],
        "vocal_advice": template["vocal_advice"],
        "practice": template["practice"],
        "technical_evidence": evidence or {},
    }


def to_user_facing_strength(strength_type: str, evidence: dict | None = None) -> dict:
    """
    강점 레이블을 사용자 표시용 dict로 변환한다.

    Parameters
    ----------
    strength_type : "pitch_stable", "balanced_low_mid" 등 강점 레이블
    evidence      : LLM에 전달할 기술적 근거 수치 dict (선택)
    """
    template = USER_FACING_STRENGTH_TEXT.get(strength_type)
    if not template:
        return {
            "type": strength_type,
            "display_title": "잘 유지되고 있는 부분",
            "message": "현재의 안정적인 감각을 유지하세요.",
            "keep_advice": "현재의 안정적인 감각을 유지하세요.",
            "technical_evidence": evidence or {},
        }

    return {
        "type": strength_type,
        "display_title": template["display_title"],
        "message": template["message"],
        "keep_advice": template["keep_advice"],
        "technical_evidence": evidence or {},
    }


def build_user_facing_assessment(
    detected_issues: list[str],
    frequency_features: dict | None = None,
    pitch_features: dict | None = None,
) -> dict:
    """
    감지된 이슈 레이블 목록을 기반으로
    user_facing_issues 와 user_facing_strengths 를 생성한다.

    Parameters
    ----------
    detected_issues   : detect_issues() 반환값 (레이블 문자열 목록)
    frequency_features: band_energy_db 등 주파수 피처 (근거 수치용)
    pitch_features    : pitch 피처 (근거 수치용)
    """
    freq = frequency_features or {}
    pitch = pitch_features or {}
    band = freq.get("band_energy_db", {})

    user_facing_issues = []
    for issue_type in detected_issues:
        # 이슈별 기술 근거 수치 구성
        evidence: dict = {}
        if issue_type in ("low_mid_heavy", "boxy_resonance", "presence_weak", "airiness_weak"):
            band_key_map = {
                "low_mid_heavy":  "80_250",
                "boxy_resonance": "500_800",
                "presence_weak":  "2500_4000",
                "airiness_weak":  "6000_10000",
            }
            key = band_key_map[issue_type]
            if key in band:
                evidence["band"] = key
                evidence["band_energy_db"] = round(band[key], 1)
        elif issue_type in ("pitch_unstable", "low_voiced_ratio"):
            stability = pitch.get("pitch_stability_cents")
            if stability is not None:
                evidence["pitch_stability_cents"] = round(stability, 1)
            voiced = pitch.get("voiced_ratio")
            if voiced is not None:
                evidence["voiced_ratio"] = round(voiced, 3)

        user_facing_issues.append(to_user_facing_issue(issue_type, evidence))

    # 이슈가 없는 항목 → 강점으로 표시
    issue_set = set(detected_issues)
    user_facing_strengths = []
    for issue_type, strength_type in _ISSUE_TO_STRENGTH.items():
        if issue_type not in issue_set:
            evidence: dict = {}
            if issue_type in ("pitch_unstable", "low_voiced_ratio"):
                stability = pitch.get("pitch_stability_cents")
                if stability is not None:
                    evidence["pitch_stability_cents"] = round(stability, 1)
                voiced = pitch.get("voiced_ratio")
                if voiced is not None:
                    evidence["voiced_ratio"] = round(voiced, 3)
            elif issue_type in ("low_mid_heavy", "boxy_resonance", "presence_weak", "airiness_weak"):
                band_key_map = {
                    "low_mid_heavy":  "80_250",
                    "boxy_resonance": "500_800",
                    "presence_weak":  "2500_4000",
                    "airiness_weak":  "6000_10000",
                }
                key = band_key_map[issue_type]
                if key in band:
                    evidence["band"] = key
                    evidence["band_energy_db"] = round(band[key], 1)
            user_facing_strengths.append(to_user_facing_strength(strength_type, evidence))

    return {
        "user_facing_issues": user_facing_issues,
        "user_facing_strengths": user_facing_strengths,
    }

# -*- coding: utf-8 -*-
"""Single source of truth for audit report display labels (presentation only)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional


GENERATED_BASENAMES = {
    "analysis.wav",
    "preview.wav",
    "processed.wav",
    "vocals.wav",
    "no_vocals.wav",
    "audio.wav",
    "attempt_1.wav",
    "input_converted.wav",
    "input_preprocessed.wav",
    "analysis.webm",
}

FOCUS_KO = {
    "REGISTER_CONNECTION": "성구 연결",
    "EFFORT": "힘 사용",
    "STABILITY": "안정성",
    "PRESENCE": "중역 존재감",
    "BRIGHTNESS": "밝기",
    "BREATHINESS": "숨 섞임",
    "CONTACT": "접촉감",
    "DYNAMICS": "강약",
    "HIGH_NOTE": "고음 접근",
    "TIMBRE": "음색",
    "STYLE": "목표 음색",
    "SAFETY": "안전",
    "MAINTAIN": "현재 유지",
    "PHRASE_ENDURANCE": "구절 유지",
    "VIBRATO_CONTROL": "비브라토",
    "TEXTURE": "질감",
}

EFFORT_DISPLAY = {
    "LOW": "낮은 편",
    "MODERATE": "중간 정도",
    "HIGH": "높은 편",
    "UNKNOWN": "확인 부족",
    "UNAVAILABLE": "확인 부족",
}

REGISTER_CONNECTION_DISPLAY = {
    "CONNECTED": "자연스럽게 연결되는 편",
    "PARTIAL": "일부 구간만 연결",
    "DISRUPTED": "전환이 급격한 편",
    "UNRESOLVED": "연결 판단 부족",
    "UNKNOWN": "확인 부족",
    "UNAVAILABLE": "확인 부족",
}

SOURCE_BALANCE_DISPLAY = {
    "CHEST_LEANING": "흉성 쪽 음향 성향",
    "CHEST_DOMINANT": "흉성 쪽 음향 성향이 강한 편",
    "HEAD_LEANING": "두성 쪽 음향 성향",
    "HEAD_DOMINANT": "두성 쪽 음향 성향이 강한 편",
    "MIX_LIKE": "혼합에 가까운 음향 성향",
    "MIX_LIKE_CHEST_DOMINANT": "흉성 쪽 혼합 음향 성향",
    "BALANCED": "흉성·두성 음향 성향이 균형적인 편",
    "BALANCED_ACOUSTIC": "흉성·두성 음향 성향이 균형적인 편",
    "CONFLICTED": "구간마다 성향이 다른 편",
    "UNKNOWN": "확인 부족",
    "UNAVAILABLE": "확인 부족",
}

CONTACT_DISPLAY = {
    "FIRM": "단단한 편",
    "LIGHT": "가벼운 편",
    "MID": "중간 편",
    "AMBIGUOUS": "판단 부족",
    "UNKNOWN": "확인 부족",
    "UNAVAILABLE": "확인 부족",
}

BREATHINESS_DISPLAY = {
    "LOW": "적은 편",
    "HIGH": "많은 편",
    "MID": "중간 편",
    "UNKNOWN": "확인 부족",
    "UNAVAILABLE": "확인 부족",
}

STABILITY_DISPLAY = {
    "STABLE": "안정적인 편",
    "UNSTABLE": "흔들림이 있는 편",
    "UNSTABLE_LIKE": "흔들림이 있는 편",
    "UNKNOWN": "확인 부족",
    "UNAVAILABLE": "확인 부족",
}

PRESENCE_DISPLAY = {
    "LOW": "낮은 편",
    "MID": "중간 편",
    "HIGH": "높은 편",
    "UNKNOWN": "확인 부족",
    "UNAVAILABLE": "확인 부족",
}

BRIGHTNESS_DISPLAY = {
    "LOW": "어두운 편",
    "MID": "중간 편",
    "HIGH": "밝은 편",
    "UNKNOWN": "확인 부족",
    "UNAVAILABLE": "확인 부족",
}

AIRINESS_DISPLAY = dict(PRESENCE_DISPLAY)

MATCH_DISPLAY = {
    "MATCH": "일치",
    "PARTIAL_MATCH": "부분 일치",
    "MISS": "불일치",
    "UNAVAILABLE": "분석 부족",
    "NOT_LABELED": "라벨 없음",
}

AXIS_TITLE_KO = {
    "effort": "힘 사용",
    "contact": "접촉감",
    "breathiness": "숨 섞임",
    "register_connection": "성구 연결",
    "source_balance": "흉성·두성 음향 성향",
    "stability": "안정성",
    "presence": "중역 존재감",
    "brightness": "밝기",
    "airiness": "음색의 공기감",
    "texture": "질감",
    "harmonic_concentration": "배음 집중",
    "timbre_consistency": "음색 일관성",
    "high_note": "고음 분석",
}


def _norm(v: Any) -> str:
    return str(v or "").strip().upper()


def display_effort(raw: Any) -> str:
    return EFFORT_DISPLAY.get(_norm(raw), "확인 부족" if not raw else str(raw))


def display_register_connection(raw: Any) -> str:
    return REGISTER_CONNECTION_DISPLAY.get(_norm(raw), "확인 부족" if not raw else str(raw))


def display_source_balance(raw: Any) -> str:
    return SOURCE_BALANCE_DISPLAY.get(_norm(raw), "확인 부족" if not raw else str(raw))


def display_contact(raw: Any) -> str:
    return CONTACT_DISPLAY.get(_norm(raw), "확인 부족" if not raw else str(raw))


def display_breathiness(raw: Any) -> str:
    return BREATHINESS_DISPLAY.get(_norm(raw), "확인 부족" if not raw else str(raw))


def display_stability(raw: Any) -> str:
    return STABILITY_DISPLAY.get(_norm(raw), "확인 부족" if not raw else str(raw))


def display_presence(raw: Any) -> str:
    return PRESENCE_DISPLAY.get(_norm(raw), "확인 부족" if not raw else str(raw))


def display_brightness(raw: Any) -> str:
    return BRIGHTNESS_DISPLAY.get(_norm(raw), "확인 부족" if not raw else str(raw))


def display_airiness(raw: Any) -> str:
    return AIRINESS_DISPLAY.get(_norm(raw), "확인 부족" if not raw else str(raw))


def display_focus(raw: Any) -> str:
    k = _norm(raw)
    return FOCUS_KO.get(k, str(raw or "—"))


def display_match(raw: Any) -> str:
    return MATCH_DISPLAY.get(_norm(raw), str(raw or "—"))


def display_axis_value(axis: str, raw: Any) -> str:
    axis = str(axis or "").lower()
    mapping = {
        "effort": display_effort,
        "register_connection": display_register_connection,
        "register": display_register_connection,
        "source_balance": display_source_balance,
        "contact": display_contact,
        "breathiness": display_breathiness,
        "stability": display_stability,
        "presence": display_presence,
        "brightness": display_brightness,
        "airiness": display_airiness,
    }
    fn = mapping.get(axis)
    if fn:
        return fn(raw)
    return str(raw or "확인 부족")


def axis_explanation(axis: str, raw: Any) -> str:
    """Longer Korean explanation matching display state."""
    st = _norm(raw)
    axis = str(axis or "").lower()
    explanations = {
        ("effort", "LOW"): "이번 녹음에서는 힘을 크게 밀어붙이는 음향 특징이 두드러지지 않았어요.",
        ("effort", "MODERATE"): "일부 구간에서 힘이 증가하는 특징이 관찰됐어요.",
        ("effort", "HIGH"): "힘을 크게 밀어붙이는 음향 특징이 비교적 뚜렷했어요.",
        ("effort", "UNKNOWN"): "힘 사용 관련 지표를 이번 녹음만으로 단정하기 어려워요.",
        ("contact", "FIRM"): "접촉 관련 음향 특성이 단단한 쪽에 가까워요.",
        ("contact", "LIGHT"): "접촉 관련 음향 특성이 가벼운 쪽에 가까워요.",
        ("contact", "MID"): "접촉 관련 음향 특성이 중간 쪽에 가까워요.",
        ("breathiness", "LOW"): "숨결이 많이 섞이는 패턴은 두드러지지 않았어요.",
        ("breathiness", "HIGH"): "숨결이 많이 섞이는 패턴이 두드러졌어요.",
        ("register_connection", "CONNECTED"): "음역이 바뀔 때 발성 특성이 비교적 연속적으로 이어졌어요.",
        ("register_connection", "PARTIAL"): "일부 구간에서는 이어지지만 전체 음역에서 일관되게 연결되지는 않았어요.",
        ("register_connection", "DISRUPTED"): "특정 음역 전환에서 발성 특성이 급격하게 달라지는 구간이 있었어요.",
        ("register_connection", "UNRESOLVED"): "성구 연결을 이번 녹음만으로 단정하기 어려워요.",
        ("source_balance", "CHEST_LEANING"): "이번 녹음에서는 흉성 쪽 음향 성향이 더 두드러졌어요.",
        ("source_balance", "CHEST_DOMINANT"): "이번 녹음에서는 흉성 쪽 음향 성향이 강하게 나타났어요.",
        ("source_balance", "HEAD_LEANING"): "이번 녹음에서는 두성 쪽 음향 성향이 더 두드러졌어요.",
        ("source_balance", "HEAD_DOMINANT"): "이번 녹음에서는 두성 쪽 음향 성향이 강하게 나타났어요.",
        ("source_balance", "BALANCED"): "흉성·두성 음향 성향이 비교적 균형적으로 나타났어요.",
        ("source_balance", "BALANCED_ACOUSTIC"): "흉성·두성 음향 성향이 비교적 균형적으로 나타났어요.",
        ("source_balance", "CONFLICTED"): "구간마다 흉성·두성 음향 성향이 다르게 나타났어요.",
        ("stability", "STABLE"): "지속되는 소리의 안정성이 비교적 유지됐어요.",
        ("stability", "UNSTABLE"): "일부 구간에서 소리가 흔들리거나 불안정한 패턴이 있었어요.",
        ("presence", "LOW"): "중역에서 소리 존재감이 낮게 나타났어요.",
        ("presence", "HIGH"): "중역에서 소리 존재감이 분명하게 나타났어요.",
        ("presence", "MID"): "중역 존재감이 중간 정도로 나타났어요.",
        ("brightness", "LOW"): "전체 주파수 분포가 상대적으로 어두운 쪽으로 나타났어요.",
        ("brightness", "HIGH"): "전체 주파수 분포가 상대적으로 밝은 쪽으로 나타났어요.",
        ("brightness", "MID"): "밝기가 중간 정도로 나타났어요.",
    }
    if (axis, st) in explanations:
        return explanations[(axis, st)]
    if st in ("UNKNOWN", "UNAVAILABLE", "UNRESOLVED", ""):
        return "이번 녹음에서 단정하기 어려워요."
    return display_axis_value(axis, raw)


def short_id(audio_id: str = "", sha256: str = "") -> str:
    src = sha256 or audio_id or ""
    return src[:8] if src else ""


def is_generated_basename(name: str) -> bool:
    return Path(name).name.lower() in GENERATED_BASENAMES


def pick_original_basename(
    path: str,
    *,
    aliases: Optional[list[str]] = None,
    original_filename: Optional[str] = None,
) -> str:
    """Prefer user-facing original filename over generated/runtime names."""
    if original_filename and not is_generated_basename(original_filename):
        return Path(original_filename).name
    candidates: list[str] = []
    if path:
        candidates.append(Path(path).name)
    for a in aliases or []:
        if a:
            candidates.append(Path(a).name)
    # Prefer non-generated, non-upload names
    for name in candidates:
        low = name.lower()
        if is_generated_basename(name):
            continue
        if low in ("upload.wav", "upload.m4a", "upload.mp3", "upload.webm"):
            continue
        return name
    # upload.* with short id later
    for name in candidates:
        if name:
            return name
    return ""


def display_audio_name(
    *,
    path: str = "",
    audio_id: str = "",
    sha256: str = "",
    aliases: Optional[list[str]] = None,
    original_filename: Optional[str] = None,
    human_name: Optional[str] = None,
    duplicate_basenames: Optional[set[str]] = None,
) -> str:
    """Human-facing title. Hash is never the primary title when a filename exists."""
    base = pick_original_basename(
        path, aliases=aliases, original_filename=original_filename
    )
    sid = short_id(audio_id, sha256)
    if not base:
        return human_name or audio_id or sid or "unknown"
    # upload.m4a alone → disambiguate
    if base.lower().startswith("upload."):
        return f"{base} · {sid}" if sid else base
    dup = duplicate_basenames or set()
    if base in dup and sid:
        return f"{base} · {sid}"
    return base


def sanitize_filename_stem(display_name: str, audio_id: str = "") -> str:
    stem = Path(display_name).stem if display_name else audio_id
    # strip short-id suffix " · abcd1234"
    stem = re.sub(r"\s*·\s*[0-9a-fA-F]{6,}\s*$", "", stem)
    stem = re.sub(r"[^\w가-힣\-]+", "_", stem, flags=re.UNICODE)
    stem = re.sub(r"_+", "_", stem).strip("_")
    return (stem or audio_id or "audio")[:60]


def build_duplicate_basename_set(paths: list[str]) -> set[str]:
    from collections import Counter

    names = []
    for p in paths:
        n = pick_original_basename(p)
        if n and not is_generated_basename(n) and not n.lower().startswith("upload."):
            names.append(n)
    counts = Counter(names)
    return {n for n, c in counts.items() if c > 1}


def natural_one_line_summary(canonical: dict[str, Any]) -> str:
    """2–3 sentence Korean summary: maintained / limitation / timbre (no raw concat)."""
    effort = _norm((canonical.get("effort") or {}).get("status"))
    effort_rel = bool((canonical.get("effort") or {}).get("reliable"))
    contact = _norm((canonical.get("contact") or {}).get("status"))
    breath = _norm((canonical.get("breathiness") or {}).get("status"))
    reg = _norm((canonical.get("register_connection") or {}).get("status"))
    stab = _norm((canonical.get("stability") or {}).get("status"))
    presence = _norm((canonical.get("presence") or {}).get("status"))
    brightness = _norm((canonical.get("brightness") or {}).get("status"))

    m_parts: list[str] = []
    if contact == "FIRM":
        m_parts.append("접촉감은 단단한 편")
    elif contact == "LIGHT":
        m_parts.append("접촉감은 가벼운 편")
    if breath == "LOW":
        m_parts.append("숨 섞임은 적은 편")
    elif breath == "HIGH":
        m_parts.append("숨 섞임은 많은 편")
    if effort_rel and effort == "LOW":
        m_parts.append("힘 사용은 낮은 편")

    sentences: list[str] = []
    if len(m_parts) == 1:
        sentences.append(f"{m_parts[0]}이에요.")
    elif len(m_parts) == 2:
        # Prefer fixed natural pairs over morphological hacks
        a, b = m_parts[0], m_parts[1]
        if a == "접촉감은 단단한 편" and b.startswith("숨 섞임"):
            sentences.append(f"접촉감은 단단하고 {b}이에요.")
        elif a == "접촉감은 가벼운 편" and b.startswith("숨 섞임"):
            sentences.append(f"접촉감은 가볍고 {b}이에요.")
        else:
            sentences.append(f"{a}이고 {b}이에요.")
    elif len(m_parts) >= 3:
        sentences.append(f"{m_parts[0]}이고 {m_parts[1]}이며 {m_parts[2]}이에요.")

    lim_bits: list[str] = []
    if reg == "DISRUPTED":
        lim_bits.append("성구 연결은 전환이 급격한 편이에요")
    elif reg == "PARTIAL":
        lim_bits.append("성구 연결은 일부 구간에서만 안정적으로 이어졌어요")
    if stab in ("UNSTABLE", "UNSTABLE_LIKE"):
        lim_bits.append("일부 구간에서 발성 안정성이 떨어졌어요")
    if effort_rel and effort in ("HIGH", "MODERATE"):
        lim_bits.append(f"힘 사용은 {display_effort(effort)}로 나타났어요")

    if lim_bits or stab == "STABLE":
        if stab == "STABLE" and lim_bits:
            first = lim_bits[0]
            extra = lim_bits[1:]
            if extra:
                joined = first
                if joined.endswith("이어졌어요"):
                    joined = joined.replace("이어졌어요", "이어졌고")
                elif joined.endswith("이에요"):
                    joined = joined[:-3] + "이고"
                rest = " ".join(e if e.endswith(("요", "요.")) else e + "." for e in extra)
                sentences.append(f"발성 안정성은 비교적 유지되지만, {joined}. {rest}")
            else:
                sentences.append(f"발성 안정성은 비교적 유지되지만, {first}.")
        elif lim_bits:
            for bit in lim_bits[:2]:
                if bit.endswith(("요", "요.")):
                    sentences.append(bit if bit.endswith(".") else bit + ".")
                else:
                    sentences.append(f"{bit}이에요.")
        elif stab == "STABLE":
            sentences.append("발성 안정성은 비교적 유지됐어요.")

    t_parts: list[str] = []
    if presence == "LOW":
        t_parts.append("중역 존재감은 낮은 쪽")
    elif presence == "HIGH":
        t_parts.append("중역 존재감은 분명한 쪽")
    if brightness == "LOW":
        t_parts.append("밝기는 어두운 쪽")
    elif brightness == "HIGH":
        t_parts.append("밝기는 밝은 쪽")
    if len(t_parts) == 1:
        sentences.append(f"{t_parts[0]}으로 나타났어요.")
    elif len(t_parts) >= 2:
        sentences.append(f"{t_parts[0]}이고 {t_parts[1]}으로 나타났어요.")

    if not sentences:
        return "이번 녹음에서는 뚜렷한 발성 특징을 하나로 좁히기 어려워요."
    out = " ".join(s.strip() for s in sentences if s.strip())
    for tok in ("CONNECTED", "PARTIAL", "DISRUPTED", "CHEST_DOMINANT", "HEAD_LEANING"):
        out = out.replace(tok, "")
    return " ".join(out.split())


def salient_display_items(salient: list[dict[str, Any]]) -> list[str]:
    out = []
    for feat in salient or []:
        axis = str(feat.get("axis") or "")
        status = feat.get("status")
        st = _norm(status)
        # Prefer natural phrasing over "axis + raw"
        if axis == "register_connection":
            if st == "PARTIAL":
                out.append("성구 연결이 일부 구간에서만 안정적")
            elif st == "DISRUPTED":
                out.append("성구 연결 전환이 급격한 편")
            elif st == "CONNECTED":
                out.append("성구 연결이 자연스럽게 이어지는 편")
            else:
                out.append(f"성구 연결: {display_register_connection(status)}")
        elif axis == "contact":
            out.append(f"접촉감이 {display_contact(status)}")
        elif axis == "brightness":
            out.append(f"밝기가 {display_brightness(status)}")
        elif axis == "presence":
            out.append(f"중역 존재감이 {display_presence(status)}")
        elif axis == "breathiness":
            out.append(f"숨 섞임이 {display_breathiness(status)}")
        elif axis == "effort":
            out.append(f"힘 사용이 {display_effort(status)}")
        elif axis == "source_balance":
            out.append(f"흉성·두성 음향 성향: {display_source_balance(status)}")
        elif axis == "stability":
            out.append(f"안정성이 {display_stability(status)}")
        else:
            title = AXIS_TITLE_KO.get(axis, axis)
            label = display_axis_value(axis, status)
            out.append(f"{title}: {label}")
    return out


def glossary_markdown() -> str:
    return """### 용어 설명

**힘 사용**  
소리를 밀어붙이는 것과 일치할 수 있는 음향 특징입니다.

**성구 연결**  
음역이 올라갈 때 발성 특성이 얼마나 연속적으로 이어지는지입니다.

**흉성·두성 음향 성향**  
이번 녹음이 흉성 쪽/두성 쪽 음향 특성 중 어느 쪽에 가까운지입니다.

중요: **성구 연결과 흉성/두성 성향은 서로 다른 개념**입니다. 흉성 쪽 성향이 강해도 성구 연결은 자연스러울 수 있고, 두성 쪽 성향이어도 전환이 급격할 수 있습니다.

#### 성구 연결 상태

- **자연스럽게 연결되는 편**: 음역 변화 중 발성 특성이 비교적 연속적입니다.
- **일부 구간만 연결**: 일부는 이어지지만 전체에서 일관적이지 않습니다.
- **전환이 급격한 편**: 특정 음역 전환에서 발성 특성이 급격하게 달라집니다.
- **연결 판단 부족 / 확인 부족**: 이번 녹음만으로 단정하기 어렵습니다.
"""

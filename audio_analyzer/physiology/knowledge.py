"""
physiology/knowledge.py
-----------------------
Anatomy/physiology knowledge for explanation — NOT direct EMG inference targets.
"""

ALTERNATIVE_POOL = [
    "의도적으로 작은 목소리 사용",
    "마이크 주파수 응답 / 녹음 거리",
    "배경 소음 또는 압축",
    "모음 발음(/a/, /i/) 차이",
    "해당 Task 수행 방법 차이",
    "일시적 피로",
    "F0 / SPL / register 차이",
]

LIMITATIONS_POOL = [
    "이 녹음만으로 성대의 실제 구조나 병변을 확인할 수 없습니다.",
    "특정 내후두근(TA/CT/LCA/IA/PCA) 활성도를 직접 측정하지 않습니다.",
    "후두 위치·혀 위치를 영상으로 관찰하지 않습니다.",
    "내부 confidence 숫자는 임상 확률이 아니라 엔지니 값입니다.",
]

NOT_IDENTIFIABLE_FROM_AUDIO = [
    "actual vocal fold lesion",
    "nodules / polyps",
    "glottal gap geometry / posterior gap",
    "mucosal wave",
    "vocal fold thickness",
    "exact larynx height",
    "exact tongue-root tension",
    "exact jaw muscular tension",
    "TA activation",
    "CT activation",
    "LCA activation",
    "IA activation",
    "PCA activation",
    "true subglottal pressure",
    "lung volume",
    "abdominal muscle activation",
    "diaphragmatic activation",
]

SYSTEM_OVERVIEW = """
Respiratory system (폐·횡격막·늑간근·복벽)
  → subglottal pressure
  → Laryngeal system (vocal folds; TA/CT/LCA/IA/PCA as explanatory structure)
  → glottal configuration / phonation
  → Vocal tract (pharynx, tongue, jaw, lips)
  → resonance / spectral shaping / projection

Acoustic audio does NOT directly equal muscle activation.
"""

"""Ensure production UI source does not contain banned technical / training copy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "miniapp" / "src"

BANNED = [
    "측정 근거 부족",
    "뚜렷한 방향 없음",
    "sustained_residual",
    "f0_continuity_ratio",
    "voiced_dropout",
    "cepstral_prominence",
    "hnr_ac_proxy",
    "raw_h1_h2",
    "onset_slope_db",
    "evidence_mass",
    "전체 발성 판단 기준",
    "30초 연습",
    "3분 연습",
    "오늘의 연습",
    "motor_cue",
    "성문 attack",
    "TA·CT",
]


def test_production_pages_have_no_banned_user_strings():
    pages = list((ROOT / "pages").glob("*.tsx")) + list((ROOT / "components").rglob("*.tsx"))
    lib = list((ROOT / "lib").glob("*.ts"))
    hits = []
    for path in pages + lib:
        text = path.read_text(encoding="utf-8")
        for token in BANNED:
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == [], hits

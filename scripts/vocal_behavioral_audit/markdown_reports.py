# -*- coding: utf-8 -*-
"""Per-audio Markdown report generation (human-readable presentation)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Optional

from audio_analyzer.diagnostic.concerns import CONCERN_CATALOG

from scripts.vocal_behavioral_audit.audio_review import actionable_limitations
from scripts.vocal_behavioral_audit.report_labels import (
    AXIS_TITLE_KO,
    build_duplicate_basename_set,
    display_audio_name,
    display_axis_value,
    display_focus,
    display_match,
    glossary_markdown,
    salient_display_items,
    sanitize_filename_stem,
    short_id,
)


CATEGORY_ORDER = [
    ("high_note", "고음"),
    ("effort", "힘·피로"),
    ("timbre", "음색"),
    ("control", "컨트롤"),
    ("safety", "안전"),
    ("other", "기타"),
]

AXIS_TABLE_ROWS = [
    ("effort", "힘 사용"),
    ("contact", "접촉감"),
    ("breathiness", "숨 섞임"),
    ("register_connection", "성구 연결"),
    ("source_balance", "흉성·두성 음향 성향"),
    ("stability", "안정성"),
    ("presence", "중역 존재감"),
    ("brightness", "밝기"),
    ("airiness", "음색의 공기감"),
    ("texture", "질감"),
    ("harmonic_concentration", "배음 집중"),
    ("timbre_consistency", "음색 일관성"),
    ("high_note", "고음 분석"),
]


def safe_stem(path: str, audio_id: str) -> str:
    return sanitize_filename_stem(Path(path).name if path else audio_id, audio_id)


def _attach_display_names(reviews: list[dict[str, Any]]) -> None:
    dups = build_duplicate_basename_set([str(r.get("file") or "") for r in reviews])
    for rev in reviews:
        info = rev.get("audio_info") or {}
        hc = rev.get("human_comparison") or {}
        name = display_audio_name(
            path=str(rev.get("file") or ""),
            audio_id=str(rev.get("audio_id") or ""),
            sha256=str(rev.get("sha256") or ""),
            original_filename=info.get("original_filename"),
            human_name=hc.get("name"),
            duplicate_basenames=dups,
        )
        rev["display_name"] = name


def write_all_markdown_reports(
    *,
    output_dir: Path,
    reviews: list[dict[str, Any]],
    singleton_by_audio: dict[str, list[dict[str, Any]]],
    target_by_audio: Optional[dict[str, list[dict[str, Any]]]] = None,
    collapse_by_audio: Optional[dict[str, dict[str, int]]] = None,
    audit_status_by_audio: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    reports_dir = output_dir / "audio_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    target_by_audio = target_by_audio or {}
    collapse_by_audio = collapse_by_audio or {}
    audit_status_by_audio = audit_status_by_audio or {}

    _attach_display_names(reviews)
    # Sort by display name for index consistency
    ordered = sorted(reviews, key=lambda r: str(r.get("display_name") or r.get("audio_id") or ""))

    index_lines = [
        "# 음원별 분석 리포트",
        "",
        f"총 **{len(ordered)}**개",
        "",
        "## 목록",
        "",
    ]
    md_paths: list[str] = []
    manual_queue: list[dict[str, Any]] = []
    path_by_audio: dict[str, str] = {}

    for i, rev in enumerate(ordered, start=1):
        aid = str(rev.get("audio_id") or f"{i:03d}")
        display = str(rev.get("display_name") or aid)
        stem = sanitize_filename_stem(display, aid)
        fname = f"audio_{i:03d}_{stem}.md"
        path = reports_dir / fname
        singles = singleton_by_audio.get(aid) or []
        targets = target_by_audio.get(aid) or []
        collapse = collapse_by_audio.get(aid) or {}
        status = audit_status_by_audio.get(aid) or _infer_status(rev, singles)
        rev["audit_review_status"] = status
        body = render_audio_markdown(
            index=i,
            review=rev,
            singletons=singles,
            targets=targets,
            collapse=collapse,
            audit_status=status,
            relative_json_hint="../concern_singletons.jsonl",
        )
        path.write_text(body, encoding="utf-8")
        md_paths.append(fname)
        path_by_audio[aid] = fname
        one = str(rev.get("one_line_summary") or "")
        if len(one) > 72:
            one = one[:69] + "…"
        hc = rev.get("human_comparison") or {}
        human_bit = ""
        if hc.get("name") or hc.get("intent"):
            human_bit = f"  - Human: `{hc.get('name') or ''}` · {', '.join(hc.get('intent') or [])}\n"
        index_lines.append(f"- **{display}**")
        index_lines.append(f"  - 한 줄: {one}")
        index_lines.append(f"  - 내부 ID: `{aid}` · 상태 **{status}**")
        if human_bit:
            index_lines.append(human_bit.rstrip("\n"))
        index_lines.append(f"  - [리포트 보기](./{fname})")
        index_lines.append("")
        if status in ("REVIEW", "FAIL") or hc.get("has_miss"):
            manual_queue.append(
                {
                    "audio_id": aid,
                    "display_name": display,
                    "file": rev.get("file"),
                    "status": status,
                    "flags": rev.get("review_flags") or [],
                    "one_line": rev.get("one_line_summary"),
                    "human_miss": hc.get("has_miss"),
                }
            )

    (reports_dir / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    summary_md = render_global_summary(ordered, manual_queue, singleton_by_audio)
    (reports_dir / "summary.md").write_text(summary_md, encoding="utf-8")

    return {
        "reports_dir": str(reports_dir),
        "count": len(md_paths),
        "index": str(reports_dir / "index.md"),
        "summary": str(reports_dir / "summary.md"),
        "files": md_paths,
        "path_by_audio": path_by_audio,
        "manual_review_queue": manual_queue,
    }


def render_audio_markdown(
    *,
    index: int,
    review: dict[str, Any],
    singletons: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    collapse: dict[str, int],
    audit_status: str,
    relative_json_hint: str,
) -> str:
    aid = review.get("audio_id")
    display = review.get("display_name") or display_audio_name(
        path=str(review.get("file") or ""),
        audio_id=str(aid or ""),
        sha256=str(review.get("sha256") or ""),
    )
    info = review.get("audio_info") or {}
    canon = review.get("canonical") or {}
    hc = review.get("human_comparison") or {}
    lines: list[str] = []
    lines.append(f"# {display}")
    lines.append("")
    lines.append(f"> 내부 ID: `{aid}`  ")
    lines.append(f"> SHA-256: `{review.get('sha256')}`  ")
    lines.append(f"> 원본 경로: `{review.get('file')}`  ")
    if hc.get("name") or hc.get("intent"):
        intent = " · ".join([str(hc.get("name") or "")] + list(hc.get("intent") or []))
        lines.append(f"> Human label: `{intent.strip(' ·')}`")
    lines.append("")
    lines.append(f"**검토 상태:** `{audit_status}`")
    lines.append("")
    lines.append("## 기본 정보")
    lines.append("")
    lines.append(f"- 음원: **{display}**")
    lines.append(f"- 길이: {info.get('duration_sec')}")
    lines.append(f"- Sample Rate: {info.get('sample_rate')}")
    lines.append(f"- Analysis status: {info.get('analysis_status')}")
    lines.append(f"- Source: {info.get('source')}")
    lines.append("")
    lines.append("## 이 음원에서 분석된 발성 특징")
    lines.append("")
    lines.append("| 항목 | 결과 | 설명 |")
    lines.append("|---|---|---|")
    for key, label in AXIS_TABLE_ROWS:
        block = canon.get(key) or {}
        raw = block.get("status")
        if key == "high_note":
            disp = "분석 가능" if block.get("available") else "분석 부족"
            desc = block.get("description") or disp
        else:
            disp = block.get("display") or display_axis_value(key, raw)
            desc = block.get("description") or axis_safe_desc(key, raw)
        lines.append(f"| {label} | {disp} | {desc} |")
    lines.append("")
    lines.append("<details><summary>내부 분석 값</summary>")
    lines.append("")
    lines.append(f"- effort: `{((canon.get('effort') or {}).get('status'))}`")
    lines.append(
        f"- register_connection: `{((canon.get('register_connection') or {}).get('status'))}`"
    )
    lines.append(f"- source_balance: `{((canon.get('source_balance') or {}).get('status'))}`")
    lines.append(f"- contact: `{((canon.get('contact') or {}).get('status'))}`")
    lines.append(f"- breathiness: `{((canon.get('breathiness') or {}).get('status'))}`")
    lines.append(f"- stability: `{((canon.get('stability') or {}).get('status'))}`")
    lines.append(f"- presence: `{((canon.get('presence') or {}).get('status'))}`")
    lines.append(f"- brightness: `{((canon.get('brightness') or {}).get('status'))}`")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append("## 한 줄 평가")
    lines.append("")
    lines.append(str(review.get("one_line_summary") or ""))
    lines.append("")
    lines.append("> 이 요약은 concern/target과 무관한 canonical song evidence만 사용합니다.")
    lines.append("")
    lines.append("## 가장 중요한 특징")
    lines.append("")
    salient_lines = salient_display_items(review.get("salient_features") or [])
    if salient_lines:
        for i, text in enumerate(salient_lines, start=1):
            lines.append(f"{i}. {text}")
    else:
        lines.append("_뚜렷한 salient feature를 좁히기 어려움_")
    lines.append("")
    lines.append("## 유지하면 좋은 특징")
    lines.append("")
    maint = review.get("maintained_features") or []
    if maint:
        for m in maint:
            lines.append(f"- {m.get('text')}")
    else:
        lines.append("_신뢰 가능한 유지 특징이 명확하지 않음_")
    lines.append("")
    limits = actionable_limitations(canon)
    if limits:
        lines.append("## 우선 확인할 부분")
        lines.append("")
        for lim in limits:
            lines.append(f"### {lim['title']}")
            lines.append("")
            lines.append(lim["body"])
            lines.append("")
    uncertain = review.get("uncertain_axes") or []
    if uncertain:
        lines.append("## 분석이 충분하지 않은 항목")
        lines.append("")
        for u in uncertain:
            label = AXIS_TITLE_KO.get(u, u)
            lines.append(f"- {label}")
        lines.append("")

    lines.append("## 고민 체크리스트 결과")
    lines.append("")
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for row in singletons:
        cid = str(row.get("concern_id") or "")
        cat = (CONCERN_CATALOG.get(cid) or {}).get("category") or "other"
        by_cat.setdefault(cat, []).append(row)
    for cat_id, cat_label in CATEGORY_ORDER:
        rows = by_cat.get(cat_id) or []
        if not rows:
            continue
        lines.append(f"### {cat_label}")
        lines.append("")
        lines.append("| 고민 | 우선 포인트 | 첫 처방 | 상태 |")
        lines.append("|---|---|---|---|")
        for r in rows:
            cid = r.get("concern_id")
            label = (CONCERN_CATALOG.get(str(cid)) or {}).get("label") or cid
            focus_ko = display_focus(r.get("primary_focus"))
            presc = ((r.get("qa") or {}).get("prescription") or {}).get("instruction") or ""
            presc_short = (presc[:48] + "…") if len(presc) > 48 else presc
            lines.append(
                f"| {label} | {focus_ko} | {presc_short or '—'} | {r.get('audit_status') or '—'} |"
            )
        lines.append("")
    lines.append("<details><summary>내부 protocol / JSON</summary>")
    lines.append("")
    lines.append(f"- singleton JSONL: `{relative_json_hint}`")
    proto_ids = sorted({str(r.get("protocol_id") or "") for r in singletons if r.get("protocol_id")})
    if proto_ids:
        lines.append(f"- protocol ids: `{', '.join(proto_ids)}`")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    focuses = sorted({display_focus(r.get("primary_focus")) for r in singletons if r.get("primary_focus")})
    lines.append("## 이 음원에서 고민에 따라 달라진 코칭")
    lines.append("")
    lines.append(f"- 우선 포인트 종류: {', '.join(focuses) or '—'}")
    lines.append(f"- Expected shared: {collapse.get('EXPECTED_SHARED_PROTOCOL', 0)}")
    lines.append(f"- Over-shared: {collapse.get('OVER_SHARED_PRESCRIPTION', 0)}")
    lines.append(f"- Wrong collapse: {collapse.get('WRONG_GENERIC_COLLAPSE', 0)}")
    lines.append("")

    lines.append("## 목표 음색별 반응")
    lines.append("")
    if targets:
        lines.append("| 목표 음색 | Primary | Secondary cue |")
        lines.append("|---|---|---|")
        for t in targets:
            sec = t.get("secondary_target") or (t.get("goal") or {}).get("secondary_target") or {}
            sec_id = sec.get("id") if isinstance(sec, dict) else sec
            lines.append(
                f"| {t.get('target_id')} | {display_focus(t.get('primary_focus'))} | {sec_id or '—'} |"
            )
        lines.append("")
        lines.append("목표 음색 변경에 따른 canonical acoustic mutation: **없음**")
    else:
        lines.append("_target sweep 결과 없음_")
    lines.append("")

    if hc:
        lines.append("## 사람 의도 / 평가와 비교")
        lines.append("")
        lines.append(f"- Human name: `{hc.get('name')}`")
        lines.append(f"- Intent: {', '.join(hc.get('intent') or []) or '—'}")
        if hc.get("notes"):
            lines.append(f"- Notes: {hc.get('notes')}")
        lines.append("")
        lines.append("| 항목 | 사람이 의도한 상태 | VAgent 분석 | 판정 |")
        lines.append("|---|---|---|---|")
        for row in hc.get("axis_comparison") or []:
            axis = row.get("axis")
            title = AXIS_TITLE_KO.get(str(axis), axis)
            human = row.get("human")
            analyzer = row.get("analyzer")
            h_disp = display_axis_value(str(axis), human) if human else "—"
            a_disp = display_axis_value(str(axis), analyzer) if analyzer else "—"
            if human:
                h_disp = f"{h_disp} (`{human}`)"
            if analyzer:
                a_disp = f"{a_disp} (`{analyzer}`)"
            lines.append(
                f"| {title} | {h_disp} | {a_disp} | {display_match(row.get('result'))} |"
            )
        lines.append("")

    lines.append("## Review flags")
    lines.append("")
    flags = review.get("review_flags") or []
    if flags:
        for f in flags:
            lines.append(f"- `{f}`")
    else:
        lines.append("_없음_")
    lines.append("")
    return "\n".join(lines)


def axis_safe_desc(key: str, raw: Any) -> str:
    from scripts.vocal_behavioral_audit.report_labels import axis_explanation

    return axis_explanation(key, raw)


def render_global_summary(
    reviews: list[dict[str, Any]],
    manual_queue: list[dict[str, Any]],
    singleton_by_audio: dict[str, list[dict[str, Any]]],
) -> str:
    lines = ["# VAgent 전체 음원 분석 요약", ""]
    lines.append(
        "| 음원 | 힘 사용 | 접촉감 | 성구 연결 | 흉성·두성 성향 | 안정성 | 중역 존재감 | 밝기 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for rev in reviews:
        c = rev.get("canonical") or {}
        name = str(rev.get("display_name") or rev.get("audio_id") or "").replace("|", "/")
        lines.append(
            f"| {name} | "
            f"{(c.get('effort') or {}).get('display') or display_axis_value('effort', (c.get('effort') or {}).get('status'))} | "
            f"{(c.get('contact') or {}).get('display') or display_axis_value('contact', (c.get('contact') or {}).get('status'))} | "
            f"{(c.get('register_connection') or {}).get('display') or display_axis_value('register_connection', (c.get('register_connection') or {}).get('status'))} | "
            f"{(c.get('source_balance') or {}).get('display') or display_axis_value('source_balance', (c.get('source_balance') or {}).get('status'))} | "
            f"{(c.get('stability') or {}).get('display') or display_axis_value('stability', (c.get('stability') or {}).get('status'))} | "
            f"{(c.get('presence') or {}).get('display') or display_axis_value('presence', (c.get('presence') or {}).get('status'))} | "
            f"{(c.get('brightness') or {}).get('display') or display_axis_value('brightness', (c.get('brightness') or {}).get('status'))} |"
        )
    lines.append("")
    lines.append("## 전체 분포")
    lines.append("")
    for axis, title in (
        ("effort", "힘 사용"),
        ("register_connection", "성구 연결"),
        ("source_balance", "흉성·두성 음향 성향"),
        ("breathiness", "숨 섞임"),
        ("presence", "중역 존재감"),
        ("brightness", "밝기"),
        ("stability", "안정성"),
        ("contact", "접촉감"),
    ):
        vals = [
            display_axis_value(axis, ((r.get("canonical") or {}).get(axis) or {}).get("status"))
            for r in reviews
        ]
        dist = Counter(vals)
        lines.append(f"### {title}")
        lines.append("")
        for k, n in dist.most_common():
            lines.append(f"- {k}: {n}")
        lines.append("")

    focus_c: Counter = Counter()
    for rows in singleton_by_audio.values():
        for r in rows:
            if r.get("primary_focus"):
                focus_c[display_focus(r["primary_focus"])] += 1
    lines.append("## 가장 자주 선택된 Coaching Focus")
    lines.append("")
    for f, n in focus_c.most_common(20):
        lines.append(f"- {f}: {n}")
    lines.append("")

    reg_vals = [
        str(((r.get("canonical") or {}).get("register_connection") or {}).get("status") or "")
        for r in reviews
    ]
    connected = sum(1 for v in reg_vals if v == "CONNECTED")
    disrupted = sum(1 for v in reg_vals if v == "DISRUPTED")
    partial = sum(1 for v in reg_vals if v == "PARTIAL")
    lines.append("## 성구 연결 메모")
    lines.append("")
    lines.append(f"- 자연스럽게 연결되는 편 (CONNECTED): {connected}")
    lines.append(f"- 일부 구간만 연결 (PARTIAL): {partial}")
    lines.append(f"- 전환이 급격한 편 (DISRUPTED): {disrupted}")
    if connected <= 1:
        lines.append("- Flag: **CONNECTED rare / DISRUPTED·PARTIAL dominant**")
    lines.append("")

    lines.append("## 사람이 직접 확인할 가치가 높은 음원")
    lines.append("")
    lines.append(f"Count: **{len(manual_queue)}**")
    lines.append("")
    for item in manual_queue[:40]:
        disp = item.get("display_name") or item.get("audio_id")
        sid = short_id(str(item.get("audio_id") or ""))
        lines.append(
            f"- **{disp}** (`{sid}`) — {item.get('status')} — miss={item.get('human_miss')}"
        )
        if item.get("one_line"):
            lines.append(f"  - {item.get('one_line')}")
    lines.append("")
    lines.append(glossary_markdown())
    return "\n".join(lines)


def _infer_status(review: dict[str, Any], singletons: list[dict[str, Any]]) -> str:
    for r in singletons:
        for f in r.get("findings") or []:
            if f.get("severity") in ("CRITICAL", "FAIL") and f.get("code") in (
                "CANONICAL_MUTATION_BY_CONCERN",
                "SAFETY_ACTIVE_EXERCISE",
                "UNSUPPORTED_ACOUSTIC_CLAIM",
                "FOCUS_PROTOCOL_MISMATCH",
                "FOCUS_PRACTICE_MISMATCH",
                "WRONG_GENERIC_COLLAPSE",
            ):
                return "FAIL"
    if (review.get("human_comparison") or {}).get("has_miss"):
        return "REVIEW"
    if "UNKNOWN_HEAVY" in (review.get("review_flags") or []):
        return "REVIEW"
    if "RARE_REGISTER_CONNECTED" in (review.get("review_flags") or []):
        return "REVIEW"
    if "RARE_BRIGHTNESS_HIGH" in (review.get("review_flags") or []):
        return "REVIEW"
    return "PASS"

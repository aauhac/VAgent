# -*- coding: utf-8 -*-
"""Write audit CSV/JSON/HTML artifacts."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from scripts.vocal_behavioral_audit.report_labels import (
    display_axis_value,
    display_audio_name,
    short_id,
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def enrich_audio_axes_display(row: dict[str, Any], *, display_name: str | None = None) -> dict[str, Any]:
    """Add *_raw / *_display columns while preserving original keys."""
    out = dict(row)
    if display_name:
        out["display_name"] = display_name
    elif not out.get("display_name"):
        out["display_name"] = display_audio_name(
            path=str(out.get("file") or ""),
            audio_id=str(out.get("audio_id") or ""),
            sha256=str(out.get("sha256") or ""),
        )

    pairs = [
        ("effort", out.get("effort_status") or out.get("effort")),
        ("register_connection", out.get("register_connection") or out.get("register")),
        ("source_balance", out.get("source_balance")),
        ("contact", out.get("contact")),
        ("breathiness", out.get("breathiness")),
        ("stability", out.get("stability")),
        ("presence", out.get("presence")),
        ("brightness", out.get("brightness")),
    ]
    for axis, raw in pairs:
        out[f"{axis}_raw"] = raw
        out[f"{axis}_display"] = display_axis_value(axis, raw)
    # Effort also kept under effort_status historically
    if "effort_status" in out or out.get("effort_raw") is not None:
        out["effort_raw"] = out.get("effort_status") or out.get("effort_raw")
        out["effort_display"] = display_axis_value("effort", out["effort_raw"])
    return out


def build_html_report(summary: dict[str, Any], *, cases_sample: list[dict[str, Any]]) -> str:
    """Self-contained offline HTML dashboard (filename-first presentation)."""
    # Normalize cases with display_name
    cases: list[dict[str, Any]] = []
    for c in cases_sample[:2000]:
        row = dict(c)
        if not row.get("display_name"):
            row["display_name"] = display_audio_name(
                path=str(row.get("file") or row.get("path") or ""),
                audio_id=str(row.get("audio_id") or ""),
                sha256=str(row.get("sha256") or ""),
                original_filename=row.get("original_filename"),
            )
        row["short_id"] = short_id(str(row.get("audio_id") or ""), str(row.get("sha256") or ""))
        cases.append(row)

    payload = {
        "summary": summary,
        "cases": cases,
        "failures": summary.get("top_failures") or [],
        "warnings": summary.get("top_warnings") or [],
    }
    data = json.dumps(payload, ensure_ascii=False)
    data = data.replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<title>VAgent Behavioral Audit — Readable Reports</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background: #0f1216; color: #e8eaed; }}
h1,h2 {{ color: #fff; }}
.cards {{ display: flex; flex-wrap: wrap; gap: 12px; }}
.card {{ background: #1a1f27; border: 1px solid #2a3340; border-radius: 10px; padding: 12px 16px; min-width: 140px; }}
.card b {{ display:block; font-size: 1.4rem; }}
.audio-card {{ background: #1a1f27; border: 1px solid #2a3340; border-radius: 10px; padding: 14px 16px; width: 280px; }}
.audio-card .title {{ font-size: 1.05rem; font-weight: 650; color: #fff; }}
.audio-card .meta {{ font-size: 12px; color: #9aa3af; margin-top: 4px; }}
.audio-card .one {{ font-size: 13px; margin-top: 8px; line-height: 1.4; }}
.muted {{ color: #9aa3af; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
th, td {{ border-bottom: 1px solid #2a3340; padding: 8px; text-align: left; vertical-align: top; }}
th {{ color: #9aa3af; font-weight: 600; }}
input, select {{ background: #11151b; color: #e8eaed; border: 1px solid #2a3340; border-radius: 6px; padding: 6px 8px; }}
.FAIL {{ color: #ff7b72; }}
.WARN {{ color: #e3b341; }}
.PASS {{ color: #3fb950; }}
.CRITICAL {{ color: #ff4d4f; font-weight: 700; }}
</style>
</head>
<body>
<h1>VAgent Behavioral Audit</h1>
<p class="muted">사람용 표시: 원본 파일명 · 한국어 축 라벨 · 내부 ID는 보조</p>
<div class="cards" id="cards"></div>
<h2>음원 카드</h2>
<input id="fName" placeholder="파일명 검색 (예: 목잡이)" style="min-width:260px; margin-bottom:10px;"/>
<div class="cards" id="audioCards"></div>
<h2>Filters</h2>
<div style="display:flex; gap:8px; flex-wrap:wrap;">
  <input id="fAudio" placeholder="파일명 또는 Audio id"/>
  <input id="fConcern" placeholder="Concern"/>
  <select id="fStatus"><option value="">Status</option><option>PASS</option><option>WARN</option><option>FAIL</option><option>REVIEW</option></select>
  <select id="fFocus"><option value="">Focus</option></select>
  <select id="fCollapse"><option value="">Collapse class</option>
    <option>EXPECTED_SHARED_PROTOCOL</option>
    <option>OVER_SHARED_PRESCRIPTION</option>
    <option>WRONG_GENERIC_COLLAPSE</option>
  </select>
  <select id="fFocusReason"><option value="">Focus reason</option>
    <option>REGISTER_EVIDENCE</option>
    <option>EFFORT_EVIDENCE</option>
    <option>STABILITY_EVIDENCE</option>
    <option>GENERAL_HIGH_NOTE_ACCESS</option>
    <option>SEMANTIC_FALLBACK</option>
  </select>
  <select id="fFallback"><option value="">fallback_used</option><option value="true">true</option><option value="false">false</option></select>
  <button id="apply">Apply</button>
</div>
<h2>Cases</h2>
<table>
<thead><tr><th>음원</th><th>ID</th><th>Concern</th><th>Focus</th><th>Protocol</th><th>Status</th><th>Score</th><th>Findings</th></tr></thead>
<tbody id="tbody"></tbody>
</table>
<h2>Top failures</h2>
<pre id="failures" style="white-space:pre-wrap;background:#1a1f27;padding:12px;border-radius:8px;"></pre>
<script>
const DATA = {data};
function esc(s) {{
  return String(s ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
}}
function hay(row) {{
  return [row.display_name, row.file, row.path, row.audio_id, row.short_id, row.original_filename]
    .map(x => String(x||'').toLowerCase()).join(' ');
}}
function renderCards() {{
  const s = DATA.summary || {{}};
  const items = [
    ['AUDIOS', s.audios],
    ['CONCERNS', (s.concerns_swept||0) + ' / ' + (s.concerns_catalog||0)],
    ['SINGLETONS', s.singleton_cases],
    ['CANONICAL MUTATIONS', s.canonical_mutations],
    ['MD REPORTS', ((s.validation_bundle||{{}}).markdown||{{}}).count || ((s.validation_finalize||{{}}).markdown_count)],
    ['HUMAN LABELED', ((s.validation_bundle||{{}}).human_validation||{{}}).labeled_audios || ((s.validation_finalize||{{}}).human_labeled)],
    ['EXPECTED SHARED', (s.collapse_classes||{{}}).EXPECTED_SHARED_PROTOCOL],
    ['OVER-SHARED', (s.collapse_classes||{{}}).OVER_SHARED_PRESCRIPTION],
    ['WRONG GENERIC', (s.collapse_classes||{{}}).WRONG_GENERIC_COLLAPSE],
    ['TRUE UNSUPPORTED', s.true_unsupported_acoustic_claims],
    ['TARGET OVERRIDE', s.target_overrides_bottleneck],
    ['FOCUS MISMATCH', s.focus_protocol_mismatches],
    ['SAFETY VIOLATIONS', s.safety_violations],
  ];
  document.getElementById('cards').innerHTML = items.map(([k,v]) =>
    `<div class="card"><span class="muted">${{k}}</span><b>${{v ?? '—'}}</b></div>`
  ).join('');
  document.getElementById('failures').textContent = JSON.stringify(DATA.failures || [], null, 2);
  const focuses = [...new Set((DATA.cases||[]).map(c => c.primary_focus || c.effort).filter(Boolean))].sort();
  const sel = document.getElementById('fFocus');
  focuses.forEach(f => {{ const o=document.createElement('option'); o.value=f; o.textContent=f; sel.appendChild(o); }});
}}
function uniqueAudios() {{
  const seen = new Map();
  for (const row of (DATA.cases||[])) {{
    const id = row.audio_id || row.display_name;
    if (!id || seen.has(id)) continue;
    seen.set(id, row);
  }}
  return [...seen.values()];
}}
function renderAudioCards() {{
  const q = (document.getElementById('fName').value || '').trim().toLowerCase();
  const rows = uniqueAudios().filter(r => !q || hay(r).includes(q)).slice(0, 120);
  document.getElementById('audioCards').innerHTML = rows.map(r => {{
    const title = esc(r.display_name || r.file || r.audio_id || '');
    const sid = esc(r.short_id || String(r.audio_id||'').slice(0,8));
    const one = esc(String(r.one_line || r.one_line_summary || '').slice(0,140));
    const md = r.md_path || r.md || '';
    const link = md ? `<div class="meta"><a style="color:#8ab4ff" href="${{esc(md)}}">리포트</a></div>` : '';
    return `<div class="audio-card">
      <div class="title">${{title}}</div>
      <div class="meta">ID: ${{sid}}</div>
      <div class="one">${{one}}</div>
      ${{link}}
    </div>`;
  }}).join('') || '<p class="muted">검색 결과 없음</p>';
}}
function renderRows() {{
  const a = document.getElementById('fAudio').value.trim().toLowerCase();
  const c = document.getElementById('fConcern').value.trim().toUpperCase();
  const st = document.getElementById('fStatus').value;
  const fo = document.getElementById('fFocus').value;
  const cc = document.getElementById('fCollapse') ? document.getElementById('fCollapse').value : '';
  const fr = document.getElementById('fFocusReason') ? document.getElementById('fFocusReason').value : '';
  const fu = document.getElementById('fFallback') ? document.getElementById('fFallback').value : '';
  const rows = (DATA.cases||[]).filter(row => {{
    if (a && !hay(row).includes(a)) return false;
    if (c && !(String(row.concern_id||'').toUpperCase().includes(c))) return false;
    if (st && (row.audit_status||row.audit_review_status) !== st) return false;
    if (fo && row.primary_focus !== fo && row.effort !== fo) return false;
    if (cc) {{
      const codes = (row.findings||[]).map(f => f.code);
      if (!codes.includes(cc) && !(row.collapse_class === cc)) return false;
    }}
    if (fr && String((row.focus_selection||{{}}).reason||'') !== fr) return false;
    if (fu === 'true' && !(row.focus_selection||{{}}).fallback_used) return false;
    if (fu === 'false' && (row.focus_selection||{{}}).fallback_used) return false;
    return true;
  }}).slice(0, 500);
  document.getElementById('tbody').innerHTML = rows.map(r => {{
    const findings = (r.findings||[]).map(f => f.code).join(', ');
    const md = r.md_path || r.md || '';
    const title = esc(r.display_name || r.file || '');
    const sid = esc(r.short_id || String(r.audio_id||'').slice(0,8));
    return `<tr>
      <td>${{title}}</td>
      <td class="muted">${{sid}}</td>
      <td>${{esc(r.concern_id||'')}}</td>
      <td>${{esc(r.primary_focus||'')}}</td>
      <td>${{esc(r.protocol_id||'')}}</td>
      <td class="${{r.audit_status||r.audit_review_status||''}}">${{esc(r.audit_status||r.audit_review_status||'')}}</td>
      <td>${{(r.audit_score||{{}}).total ?? ''}}${{r.one_line ? ' — ' + esc(String(r.one_line).slice(0,60)) : ''}}</td>
      <td>${{md ? esc(md) : esc(findings)}}</td>
    </tr>`;
  }}).join('');
}}
document.getElementById('apply').onclick = () => {{ renderRows(); renderAudioCards(); }};
document.getElementById('fName').oninput = renderAudioCards;
renderCards();
renderAudioCards();
renderRows();
</script>
</body>
</html>
"""


def distribution(values: Iterable[Any]) -> dict[str, int]:
    return dict(Counter(str(v) for v in values))

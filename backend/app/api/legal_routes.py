"""Public legal documents. No auth. Content from docs/legal markdown."""

from __future__ import annotations

import html
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["legal"])

_ROOT = Path(__file__).resolve().parents[3]
_LEGAL_DIR = _ROOT / "docs" / "legal"

_FILES = {
    "terms": "TERMS_OF_SERVICE.ko.md",
    "privacy": "PRIVACY_POLICY.ko.md",
    "privacy-consent": "PRIVACY_COLLECTION_CONSENT.ko.md",
}

_TITLES = {
    "terms": "노래 실력 진단받기 서비스 이용약관",
    "privacy": "노래 실력 진단받기 개인정보처리방침",
    "privacy-consent": "개인정보 수집·이용 동의",
}


def _md_to_html(md: str) -> str:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S).strip()
    lines = md.splitlines()
    out: list[str] = []
    i = 0

    def esc(s: str) -> str:
        return html.escape(s)

    def inline(s: str) -> str:
        s = esc(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(
            r"\[([^\]]+)\]\((https?://[^)]+)\)",
            r'<a href="\2" rel="noreferrer" target="_blank">\1</a>',
            s,
        )
        return s

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("# "):
            out.append(f"<h1>{esc(line[2:])}</h1>")
            i += 1
            continue
        if line.startswith("## "):
            out.append(f"<h2>{esc(line[3:])}</h2>")
            i += 1
            continue
        if line.startswith("### "):
            out.append(f"<h3>{esc(line[4:])}</h3>")
            i += 1
            continue
        if line.strip().startswith("|"):
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip()
                if not re.match(r"^\|?\s*:?-{3,}", raw):
                    cells = [c.strip() for c in raw.strip("|").split("|")]
                    rows.append(cells)
                i += 1
            if rows:
                head, body = rows[0], rows[1:]
                th = "".join(f"<th>{inline(c)}</th>" for c in head)
                trs = []
                for r in body:
                    trs.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
                out.append(
                    '<div class="legal-table-wrap"><table>'
                    f"<thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody>"
                    "</table></div>"
                )
            continue
        if line.strip().startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(f"<li>{inline(lines[i].strip()[2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        if re.match(r"^\d+\.\s", line.strip()):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                items.append(f"<li>{inline(re.sub(r'^\d+\.\s', '', lines[i].strip()))}</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        para = [line]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip()
            and not lines[i].startswith("#")
            and not lines[i].strip().startswith("|")
            and not lines[i].strip().startswith("- ")
            and not re.match(r"^\d+\.\s", lines[i].strip())
        ):
            para.append(lines[i])
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


def _page(slug: str) -> HTMLResponse:
    name = _FILES.get(slug)
    if not name:
        raise HTTPException(status_code=404, detail="not found")
    path = _LEGAL_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    md = path.read_text(encoding="utf-8")
    title = _TITLES[slug]
    body = _md_to_html(md)
    html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif;
      color:#191f28; background:#f7f8fa; margin:0; }}
    main {{ max-width:480px; margin:0 auto; line-height:1.7;
      padding:20px calc(20px + env(safe-area-inset-right, 0px))
        calc(56px + env(safe-area-inset-bottom, 0px))
        calc(20px + env(safe-area-inset-left, 0px)); }}
    h1 {{ font-size:1.28rem; }} h2 {{ font-size:1.05rem; margin-top:22px; }}
    .legal-table-wrap {{ overflow-x:auto; }}
    table {{ border-collapse:collapse; width:100%; font-size:0.88rem; }}
    th, td {{ border:1px solid #e5e8eb; padding:8px 10px; vertical-align:top; text-align:left; }}
    a {{ color:#3182f6; overflow-wrap:anywhere; }}
  </style>
</head>
<body>
  <main>{body}</main>
</body>
</html>"""
    return HTMLResponse(html_doc)


@router.get("/legal/terms")
def legal_terms() -> HTMLResponse:
    return _page("terms")


@router.get("/legal/privacy")
def legal_privacy() -> HTMLResponse:
    return _page("privacy")


@router.get("/legal/privacy-consent")
def legal_privacy_consent() -> HTMLResponse:
    return _page("privacy-consent")

"""API acceptance: 3 high-note concerns + skip all controlled tasks."""
from __future__ import annotations

import io
import json
import math
import struct
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

API = "http://127.0.0.1:8002"
USER = "demo-user"
ROOT = Path(__file__).resolve().parents[1]


def wav(seconds: float = 3.0, freq: float = 220.0) -> bytes:
    buf = io.BytesIO()
    sr = 44100
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(int(sr * seconds)):
            v = int(9000 * math.sin(2 * math.pi * freq * i / sr))
            frames += struct.pack("<h", v)
        wf.writeframes(frames)
    return buf.getvalue()


def req(method: str, path: str, data=None, files=None):
    url = API + path
    headers = {"X-User-Id": USER, "X-VAgent-User-Key": USER}
    if files:
        boundary = "----VAgent" + uuid.uuid4().hex
        body = b""
        for name, (fname, content, ctype) in files.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'.encode()
            body += f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n"
        for name, value in (data or {}).items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            body += str(value).encode() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        r = urllib.request.Request(url, data=body, headers=headers, method=method)
    else:
        payload = None
        if data is not None:
            payload = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        r = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            body = json.loads(raw)
        except Exception:
            body = {"detail": raw}
        return e.code, body


def find_qa(obj, path=""):
    out = []
    if isinstance(obj, dict):
        # Prefer personalized_qa.questions cards
        qs = None
        if isinstance(obj.get("personalized_qa"), dict):
            qs = obj["personalized_qa"].get("questions")
        if qs is None and path.endswith("personalized_qa"):
            qs = obj.get("questions")
        if isinstance(qs, list):
            for i, q in enumerate(qs):
                if isinstance(q, dict) and q.get("concern_id"):
                    out.append(
                        {
                            "path": f"{path}/personalized_qa/questions[{i}]",
                            "concern_id": q.get("concern_id"),
                            "guidance_level": q.get("guidance_level"),
                            "primary_focus": q.get("primary_focus"),
                            "answer": q.get("answer") or q.get("answer_hint") or "",
                            "practice": (q.get("practice") or {}).get("title")
                            if isinstance(q.get("practice"), dict)
                            else None,
                        }
                    )
            if out:
                return out
        cid = obj.get("concern_id") or obj.get("id")
        ans = obj.get("answer") or obj.get("answer_hint")
        if cid and ans and obj.get("question"):
            out.append(
                {
                    "path": path,
                    "concern_id": cid,
                    "guidance_level": obj.get("guidance_level"),
                    "primary_focus": obj.get("primary_focus"),
                    "answer": ans,
                    "practice": None,
                }
            )
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and k not in ("axes", "raw", "llm_json"):
                out.extend(find_qa(v, f"{path}/{k}"))
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            out.extend(find_qa(x, f"{path}[{i}]"))
    return out


def main():
    st, up = req(
        "POST",
        "/v1/analyses",
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY", "separate": "false"},
        files={"file": ("t.wav", wav(4.0), "audio/wav")},
    )
    assert st == 200, up
    aid = up["analysis_id"]
    body = None
    for _ in range(200):
        st, body = req("GET", f"/v1/analyses/{aid}")
        if body.get("status") == "completed":
            break
        time.sleep(0.25)
    assert body and body.get("status") == "completed", body
    req("POST", f"/v1/analyses/{aid}/mock-unlock-detail")
    st, sess = req("POST", f"/v1/diagnostic-sessions?source_analysis_id={aid}")
    assert st == 200, sess
    sid = sess["session_id"]
    req("POST", f"/v1/diagnostic-sessions/{sid}/mock-pay", data={"product_id": "diagnostic_upgrade"})
    concerns = ["HIGH_NOTE_CANNOT_REACH", "HIGH_NOTE_TOO_EFFORTFUL", "HIGH_NOTE_FLIPS"]
    st, c = req(
        "POST",
        f"/v1/diagnostic-sessions/{sid}/concerns",
        data={"diagnostic_mode": "CONCERN_FOCUSED", "user_concerns": [{"id": x} for x in concerns]},
    )
    print("concerns", st, c.get("status"), "selected", c.get("selected_tasks"))
    st, s = req("POST", f"/v1/diagnostic-sessions/{sid}/safety", data={"answers": {}})
    print("safety", st, s.get("status"), "tasks", s.get("selected_tasks"), "detail", s.get("detail"))
    st, start = req("POST", f"/v1/diagnostic-sessions/{sid}/start-controlled-recordings")
    print("start_recordings", st, start.get("status") if isinstance(start, dict) else start, start.get("detail"))
    st, fin = req(
        "POST",
        f"/v1/diagnostic-sessions/{sid}/skip-controlled-recordings",
        data={"remaining_only": False},
    )
    print("skip_controlled", st, fin.get("status") if isinstance(fin, dict) else fin, fin.get("detail"))
    st, an = req("POST", f"/v1/diagnostic-sessions/{sid}/analyze")
    print("analyze", st, an.get("status") if isinstance(an, dict) else an, an.get("detail"))

    rep = {}
    for _ in range(180):
        st, rep = req("GET", f"/v1/diagnostic-sessions/{sid}/report")
        if st == 200 and (rep.get("questions") or rep.get("status") in ("READY", "COMPLETED", "ready") or find_qa(rep)):
            if find_qa(rep) or rep.get("questions"):
                break
        time.sleep(1)

    st2, sess2 = req("GET", f"/v1/diagnostic-sessions/{sid}")
    qa = find_qa(rep)
    # dedupe by concern
    by = {}
    for q in qa:
        by[q["concern_id"]] = q

    bad_final = (
        "연습 방향을 충분히 좁히기 어려워요",
        "고음 힘 패턴을 충분히 확정하기 어려워요",
        "현재 노래에서 확인된 범위까지만 안내해요",
        "모르겠어요",
        "모르겠습니다",
    )
    results = {}
    for cid in concerns:
        q = by.get(cid) or {}
        ans = str(q.get("answer") or "")
        results[cid] = {
            "found": bool(q),
            "guidance_level": q.get("guidance_level"),
            "primary_focus": q.get("primary_focus"),
            "practice": q.get("practice"),
            "answer_preview": ans[:500],
            "ends_with_unknown": any(b in ans.split("→")[-1] for b in bad_final) if ans else True,
            "has_arrow_practice": "→" in ans,
            "skip_leads": ans.startswith("성구") or ans.startswith("추가 고음") and "범위까지만" in ans,
        }

    out = {
        "sid": sid,
        "aid": aid,
        "evidence_mode": sess2.get("evidence_mode"),
        "skipped": sess2.get("user_skipped_tasks"),
        "report_keys": list(rep.keys()),
        "qa_count": len(qa),
        "results": results,
        "pass": all(
            r["found"] and not r["ends_with_unknown"] and r["has_arrow_practice"]
            for r in results.values()
        ),
    }
    path = ROOT / "runtime" / "_guidance_v2_acceptance.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("PASS" if out["pass"] else "FAIL")


if __name__ == "__main__":
    main()

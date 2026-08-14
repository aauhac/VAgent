/**
 * QA v4 runtime browser E2E — fresh session + stale-report regenerate.
 *
 * Do not edit miniapp/vite.config.ts for this test.
 * Default: backend :8000, frontend :5173.
 * Override backend with VAGENT_E2E_API (Playwright page.route).
 *
 *   node miniapp/scripts/e2e_qa_v4_runtime_browser.mjs
 */
import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const API = process.env.VAGENT_E2E_API || 'http://127.0.0.1:8000';
const WEB = process.env.VAGENT_E2E_WEB || 'http://127.0.0.1:5173';
const USER = 'demo-user';

const CONCERNS = ['VOICE_TOO_NASAL_PERCEPT', 'VOICE_TOO_THIN', 'TIMBRE_CHANGES_HIGH'];
const TIMBRE = 'INTENSE_DISTINCT';

function py(code) {
  const r = spawnSync(path.join(ROOT, '.venv', 'Scripts', 'python.exe'), ['-c', code], {
    cwd: ROOT,
    encoding: 'utf-8',
    env: { ...process.env, PYTHONPATH: ROOT, VAGENT_ENV: 'development', RUNTIME_DIR: 'runtime' },
  });
  if (r.status !== 0) throw new Error(`python failed:\n${r.stderr || r.stdout}`);
  const line = (r.stdout || '').trim().split(/\r?\n/).filter(Boolean).pop();
  return JSON.parse(line);
}

function bootstrapFresh() {
  return py(`
import io, json, math, struct, time, wave, urllib.request, urllib.error, uuid
from pathlib import Path
API = "${API}"; USER = "${USER}"
CONCERNS = ${JSON.stringify(CONCERNS)}
TIMBRE = "${TIMBRE}"
ROOT = Path(r"${ROOT.replace(/\\/g, '\\\\')}")
def wav(seconds=3.0, freq=220.0):
    buf=io.BytesIO(); sr=44100
    with wave.open(buf,"wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        frames=bytearray()
        for i in range(int(sr*seconds)):
            v=int(9000*math.sin(2*math.pi*freq*i/sr))
            frames += struct.pack("<h", v)
        wf.writeframes(frames)
    return buf.getvalue()
def req(method, path, data=None, files=None):
    url=API+path
    headers={"X-User-Id":USER,"X-VAgent-User-Key":USER}
    if files:
        boundary="----VAgent"+uuid.uuid4().hex
        body=b""
        for name,(fname,content,ctype) in files.items():
            body+=f"--{boundary}\\r\\n".encode()
            body+=f'Content-Disposition: form-data; name="{name}"; filename="{fname}"\\r\\n'.encode()
            body+=f"Content-Type: {ctype}\\r\\n\\r\\n".encode()+content+b"\\r\\n"
        for name,value in (data or {}).items():
            body+=f"--{boundary}\\r\\n".encode()
            body+=f'Content-Disposition: form-data; name="{name}"\\r\\n\\r\\n'.encode()+str(value).encode()+b"\\r\\n"
        body+=f"--{boundary}--\\r\\n".encode()
        headers["Content-Type"]=f"multipart/form-data; boundary={boundary}"
        r=urllib.request.Request(url,data=body,headers=headers,method=method)
    else:
        payload=None
        if data is not None:
            payload=json.dumps(data).encode(); headers["Content-Type"]="application/json"
        r=urllib.request.Request(url,data=payload,headers=headers,method=method)
    try:
        with urllib.request.urlopen(r,timeout=300) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")
st,up=req("POST","/v1/analyses",data={"analysis_mode":"FUNCTIONAL","input_mode":"VOCAL_ONLY","separate":"false"},files={"file":("t.wav",wav(4.0),"audio/wav")})
assert st==200, up
aid=up["analysis_id"]; body=None
for _ in range(200):
    st,body=req("GET",f"/v1/analyses/{aid}")
    if body.get("status")=="completed": break
    time.sleep(0.25)
assert body and body.get("status")=="completed", body
# Patch canonical VF so QA v4 has the observed sample (does not retune analyzer thresholds)
p = ROOT / "runtime" / aid / "analysis.json"
data = json.loads(p.read_text(encoding="utf-8"))
vf = data.setdefault("vocal_function_profile", {})
vf["effort_assessment"] = {"severity": "LOW"}
dims = vf.setdefault("dimensions", {})
dims["vocal_effort_strain"] = {"status": "LOW"}
dims["glottal_contact_profile"] = {"status": "OBSERVED", "continuum_0_to_1": 0.72, "status_label": "단단"}
dims["air_leakage_breathiness"] = {"status": "LOW"}
dims["phonation_regularity"] = {"status": "STABLE"}
vt = vf.setdefault("vocal_type_profile", {})
vt["register_strategy"] = {"status": "PARTIAL"}
vt["canonical_register"] = {"status": "PARTIAL"}
vf["timbre_profile"] = {"available": True, "axes": {"presence": {"continuum": 0.72}, "airiness": {"continuum": 0.25}}}
vf["high_note_function_profile"] = {"available": False, "axes": {}}
p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
req("POST",f"/v1/analyses/{aid}/mock-unlock-detail")
st,sess=req("POST",f"/v1/diagnostic-sessions?source_analysis_id={aid}"); assert st==200, sess
sid=sess["session_id"]
req("POST",f"/v1/diagnostic-sessions/{sid}/mock-pay",data={"product_id":"diagnostic_upgrade"})
st,c=req("POST",f"/v1/diagnostic-sessions/{sid}/concerns",data={
    "diagnostic_mode":"CONCERN_FOCUSED",
    "user_concerns":[{"id":x} for x in CONCERNS],
    "timbre_goal":{"id": TIMBRE},
})
assert st==200, c
print(json.dumps({"session_id":sid,"analysis_id":aid,"status":c.get("status")}))
`);
}

async function withApiProxy(page) {
  await page.route('**/v1/**', async (route) => {
    const req = route.request();
    const u = new URL(req.url());
    const target = `${API}${u.pathname}${u.search}`;
    const headers = { ...req.headers(), 'x-user-id': USER, 'x-vagent-user-key': USER };
    delete headers.host;
    const init = { method: req.method(), headers };
    if (req.method() !== 'GET' && req.method() !== 'HEAD') {
      init.body = await req.postDataBuffer();
    }
    const res = await fetch(target, init);
    const buf = Buffer.from(await res.arrayBuffer());
    const outHeaders = {};
    res.headers.forEach((v, k) => {
      if (k.toLowerCase() === 'content-encoding') return;
      outHeaders[k] = v;
    });
    await route.fulfill({ status: res.status, headers: outHeaders, body: buf });
  });
}

function failOldUnknown(text) {
  return /하나로 좁히기 어려워요|직접 확정할 음향 지표는 제한적이에요/.test(text || '');
}

{
  const h = await fetch(`${API}/health`).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  if (h.status !== 'ok') {
    console.error('BACKEND_UNAVAILABLE', API, h);
    process.exit(2);
  }
}

const boot = bootstrapFresh();
const sid = boot.session_id;
const aid = boot.analysis_id;
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await withApiProxy(page);
await page.addInitScript(
  ({ user }) => {
    sessionStorage.setItem(
      'vagent_user_identity_v1',
      JSON.stringify({ provider: 'DEV', subject: user }),
    );
  },
  { user: USER },
);

await page.goto(`${WEB}/diagnostic/${sid}/safety`, { waitUntil: 'networkidle' });
await page.getByRole('button', { name: '다음' }).click();
await page.waitForURL(`**/diagnostic/${sid}/recordings`, { timeout: 20000 });
await page.getByRole('button', { name: /추가 녹음 없이 결과 보기/ }).click();
await page.getByRole('button', { name: /추가 녹음 없이 계속/ }).click();
await page.waitForURL(`**/diagnostic/${sid}/report`, { timeout: 180000 });
await page.waitForSelector('[data-testid=qa-section]', { timeout: 30000 });

const q1 = (await page.locator('[data-testid=qa-answer-0]').innerText()).trim();
const q2 = (await page.locator('[data-testid=qa-answer-1]').innerText()).trim();
const q3 = (await page.locator('[data-testid=qa-answer-2]').innerText()).trim();
const n1 = await page.locator('[data-testid=qa-next-0]').count();
const n2 = await page.locator('[data-testid=qa-next-1]').count();
const n3 = await page.locator('[data-testid=qa-next-2]').count();
const target = await page.locator('[data-testid=desired-timbre]').innerText().catch(() => '');
const practiceCount = await page.locator('[data-testid=practice-section]').count();

const repRes = await fetch(`${API}/v1/diagnostic-sessions/${sid}/report`, {
  headers: { 'X-User-Id': USER, 'X-VAgent-User-Key': USER },
});
const rep = await repRes.json();
const qs = (rep.personalized_qa && rep.personalized_qa.questions) || [];
const ids = qs.map((q) => q.concern_id);
const fakeTasks = JSON.stringify(rep.task_result_summary || []).includes('planned_task') === false;

const freshPass =
  JSON.stringify(ids) === JSON.stringify(CONCERNS)
  && !failOldUnknown(q1)
  && !failOldUnknown(q2)
  && !failOldUnknown(q3)
  && !/하나로 좁히기/.test(q3)
  && qs.every((q) => q.what_to_change && (q.action || {}).short_instruction && (q.success_cues || []).length)
  && /강렬|개성/.test(target)
  && practiceCount >= 1
  && rep.qa_guidance_version === 'precision-qa-guided-experiment-v5'
  && String(rep.evidence_mode || '').includes('CONCERN');

// Stale report: overwrite stored JSON, GET stays old, DEV regenerate upgrades
const stale = py(`
import json, urllib.request
from pathlib import Path
API="${API}"; USER="${USER}"; SID="${sid}"
ROOT=Path(r"${ROOT.replace(/\\/g, '\\\\')}")
p=ROOT/"runtime"/"diagnostic_sessions"/SID/"premium_report.json"
data=json.loads(p.read_text(encoding="utf-8"))
data["qa_guidance_version"]="precision-qa-legacy"
qs=data.setdefault("personalized_qa",{}).setdefault("questions",[])
if qs:
    qs[2]["answer"]="이번 노래만으로 음색 관련 원인을 하나로 좁히기는 어려워요."
p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
req=urllib.request.Request(API+f"/v1/diagnostic-sessions/{SID}/report", headers={"X-User-Id":USER,"X-VAgent-User-Key":USER})
with urllib.request.urlopen(req, timeout=30) as r:
    got=json.loads(r.read().decode())
print(json.dumps({"stored": got.get("qa_guidance_version")}))
`);

const regenRes = await fetch(`${API}/v1/diagnostic-sessions/${sid}/regenerate-report`, {
  method: 'POST',
  headers: { 'X-User-Id': USER, 'X-VAgent-User-Key': USER },
});
const regen = await regenRes.json();

await browser.close();

const out = {
  meta: { api: API, web: WEB, session_id: sid, analysis_id: aid, evidence_mode: rep.evidence_mode },
  qa_guidance_version: rep.qa_guidance_version,
  questions: qs.map((q, i) => ({
    concern_id: q.concern_id,
    question: q.question,
    preview: [q1, q2, q3][i],
    what_to_change: q.what_to_change,
    primary_focus: q.primary_focus,
    action: q.action,
  })),
  target,
  next_visible: [n1, n2, n3],
  practiceCount,
  stale_before: stale.stored,
  stale_after: regen.qa_guidance_version,
  pass: Boolean(
    freshPass
    && stale.stored === 'precision-qa-legacy'
    && regen.qa_guidance_version === 'precision-qa-guided-experiment-v5'
    && regenRes.status === 200,
  ),
};
const outPath = path.join(ROOT, `.e2e_qa_v4_runtime_${Date.now()}.json`);
fs.writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf-8');
console.log(JSON.stringify(out, null, 2));
process.exit(out.pass ? 0 : 1);

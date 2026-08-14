/**
 * Precision QA Guided Experiment v5 browser E2E.
 * Do not edit miniapp/vite.config.ts — use VAGENT_E2E_API override.
 *
 *   node miniapp/scripts/e2e_precision_qa_v5_browser.mjs
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
const CURRENT_QA = 'precision-qa-guided-experiment-v5';

const BAD = [
  '직접 확정할 음향 지표는 제한적',
  '뚜렷한 음향 특징이 강하지 않',
  '한 원인으로 단정하지',
  '특정 원인을 가정하기보다는',
  '하나로 좁히기 어려워요',
];

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

{
  const h = await fetch(`${API}/health`).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  if (h.status !== 'ok') {
    console.error('BACKEND_UNAVAILABLE', API, h);
    process.exit(2);
  }
  const proto = await fetch(`${API}/v1/diagnostic/protocol`).then((r) => r.json());
  if (proto.qa_guidance_version !== CURRENT_QA) {
    console.error('BACKEND_NOT_V5', proto.qa_guidance_version);
    process.exit(3);
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

const texts = [];
for (let i = 0; i < 3; i++) {
  const ans = (await page.locator(`[data-testid=qa-answer-${i}]`).innerText()).trim();
  const a = await page.locator(`[data-testid=qa-compare-${i}-a]`).innerText().catch(() => '');
  const b = await page.locator(`[data-testid=qa-compare-${i}-b]`).innerText().catch(() => '');
  const success = await page.locator(`[data-testid=qa-compare-${i}-success]`).innerText().catch(() => '');
  const next = await page.locator(`[data-testid=qa-next-${i}]`).innerText().catch(() => '');
  texts.push({ ans, a, b, success, next });
}
const goal = await page.locator('[data-testid=coaching-goal]').innerText().catch(() => '');
const target = await page.locator('[data-testid=desired-timbre]').innerText().catch(() => '');
const practiceCount = await page.locator('[data-testid=practice-section]').count();

const rep = await fetch(`${API}/v1/diagnostic-sessions/${sid}/report`, {
  headers: { 'X-User-Id': USER, 'X-VAgent-User-Key': USER },
}).then((r) => r.json());
const qs = (rep.personalized_qa && rep.personalized_qa.questions) || [];

const noBad = texts.every((t) => !BAD.some((b) => (t.ans + t.a + t.b).includes(b)));
const hasAB = texts.every((t) => /①/.test(t.a) && /②/.test(t.b));
const pass = Boolean(
  noBad
  && hasAB
  && texts.every((t) => t.success)
  && qs.every((q) => (q.comparison || q.comparison_protocol || {}).baseline_instruction)
  && /음역/.test(goal)
  && /강렬|개성/.test(target)
  && practiceCount === 1
  && rep.qa_guidance_version === CURRENT_QA
  && (rep.coaching_goal || {}).primary_focus === 'REGISTER_CONNECTION'
);

await browser.close();

const out = {
  meta: { api: API, web: WEB, session_id: sid, analysis_id: aid, evidence_mode: rep.evidence_mode },
  qa_guidance_version: rep.qa_guidance_version,
  global_goal: {
    title: (rep.coaching_goal || {}).goal_title,
    focus: (rep.coaching_goal || {}).primary_focus,
    description: (rep.coaching_goal || {}).goal_description,
  },
  target,
  practiceCount,
  questions: qs.map((q, i) => ({
    concern_id: q.concern_id,
    question: q.question,
    browser_answer: texts[i]?.ans,
    browser_a: texts[i]?.a,
    browser_b: texts[i]?.b,
    browser_success: texts[i]?.success,
    what_to_change: q.what_to_change,
    comparison: q.comparison || q.comparison_protocol,
    primary_focus: q.primary_focus,
    response_mode: q.response_mode || q.answer_mode,
  })),
  pass,
};
const outPath = path.join(ROOT, `.e2e_precision_qa_v5_${Date.now()}.json`);
fs.writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf-8');
console.log(JSON.stringify({ ...out, artifact: outPath }, null, 2));
process.exit(out.pass ? 0 : 1);

/**
 * Guidance v2 browser: 3 high-note concerns + skip all controlled tasks → report.
 * Asserts Q answers are actionable (not skip/unknown finals).
 *
 * Do not edit miniapp/vite.config.ts for this test.
 * Override backend with VAGENT_E2E_API (page route) or VITE_API_PROXY_TARGET.
 *
 *   set VAGENT_E2E_API=http://127.0.0.1:8002
 *   node miniapp/scripts/e2e_guidance_v2_browser.mjs
 */
import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const API = process.env.VAGENT_E2E_API || 'http://127.0.0.1:8002';
const WEB = process.env.VAGENT_E2E_WEB || 'http://127.0.0.1:5173';
const USER = 'demo-user';

function makeToneWavB64(seconds = 4.0, freq = 220) {
  const code = `
import base64, io, math, struct, wave
sr=44100; n=int(sr*${seconds}); buf=io.BytesIO()
with wave.open(buf,'wb') as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
    frames=bytearray()
    for i in range(n):
        v=int(12000*math.sin(2*math.pi*${freq}*i/sr))
        frames += struct.pack('<h', v)
    wf.writeframes(frames)
print(base64.b64encode(buf.getvalue()).decode())
`;
  const r = spawnSync(path.join(ROOT, '.venv', 'Scripts', 'python.exe'), ['-c', code], {
    cwd: ROOT,
    encoding: 'utf-8',
  });
  if (r.status !== 0) throw new Error(r.stderr || r.stdout);
  return (r.stdout || '').trim();
}

function pySession() {
  const code = `
import io, json, math, struct, time, wave, urllib.request, urllib.error, uuid
API = "${API}"; USER = "${USER}"
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
req("POST",f"/v1/analyses/{aid}/mock-unlock-detail")
st,sess=req("POST",f"/v1/diagnostic-sessions?source_analysis_id={aid}"); assert st==200, sess
sid=sess["session_id"]
req("POST",f"/v1/diagnostic-sessions/{sid}/mock-pay",data={"product_id":"diagnostic_upgrade"})
concerns=["HIGH_NOTE_CANNOT_REACH","HIGH_NOTE_TOO_EFFORTFUL","HIGH_NOTE_FLIPS"]
st,c=req("POST",f"/v1/diagnostic-sessions/{sid}/concerns",data={"diagnostic_mode":"CONCERN_FOCUSED","user_concerns":[{"id":x} for x in concerns]})
assert st==200, c
print(json.dumps({"session_id":sid,"status":c.get("status"),"analysis_id":aid,"api":API}))
`;
  const r = spawnSync(path.join(ROOT, '.venv', 'Scripts', 'python.exe'), ['-c', code], {
    cwd: ROOT,
    encoding: 'utf-8',
    env: { ...process.env, PYTHONPATH: ROOT, VAGENT_ENV: 'development', RUNTIME_DIR: 'runtime' },
  });
  if (r.status !== 0) throw new Error(`bootstrap failed:\n${r.stderr || r.stdout}`);
  const line = (r.stdout || '').trim().split(/\r?\n/).filter(Boolean).pop();
  return JSON.parse(line);
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

async function main() {
  const h = await fetch(`${API}/health`).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  if (h.status !== 'ok') {
    console.error('BACKEND_UNAVAILABLE', API, h);
    process.exit(2);
  }
  const wavB64 = makeToneWavB64(4.2, 220);
  const boot = pySession();
  const sid = boot.session_id;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await withApiProxy(page);
  await page.addInitScript(
    ({ user, wavB64: b64 }) => {
      sessionStorage.setItem(
        'vagent_user_identity_v1',
        JSON.stringify({ provider: 'DEV', subject: user }),
      );
      window.__E2E_WAV_B64__ = b64;
    },
    { user: USER, wavB64 },
  );

  await page.goto(`${WEB}/diagnostic/${sid}/safety`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: '다음' }).click();
  await page.waitForURL(`**/diagnostic/${sid}/recordings`, { timeout: 20000 });
  await page.getByRole('button', { name: /추가 녹음 없이 결과 보기/ }).click();
  await page.getByRole('button', { name: /추가 녹음 없이 계속/ }).click();
  await page.waitForURL(`**/diagnostic/${sid}/report`, { timeout: 180000 });

  const bodyText = await page.locator('body').innerText();
  const repRes = await fetch(`${API}/v1/diagnostic-sessions/${sid}/report`, {
    headers: { 'X-User-Id': USER, 'X-VAgent-User-Key': USER },
  });
  const rep = await repRes.json();
  const qs = (rep.personalized_qa && rep.personalized_qa.questions) || [];
  const bad = [
    '모르겠어요',
    '모르겠습니다',
    '연습 방향을 충분히 좁히기 어려워요.',
    '고음 힘 패턴을 충분히 확정하기 어려워요.',
    '현재 노래에서 확인된 범위까지만 안내해요.',
  ];
  const checks = qs.map((q) => {
    const ans = String(q.answer || '');
    const after = ans.split('→').slice(1).join('→');
    const badFinal = bad.some((b) => after.includes(b) || (!ans.includes('→') && ans.includes(b)));
    const skipLeads = /^(성구 연결 확인 과제를 건너뛰어|추가 고음 과제를 진행하지 않아)/.test(ans.trim());
    return {
      concern_id: q.concern_id,
      guidance_level: q.guidance_level,
      primary_focus: q.primary_focus,
      has_arrow: ans.includes('→'),
      bad_final: badFinal,
      skip_leads: skipLeads,
      answer_preview: ans.slice(0, 280),
    };
  });

  const uiHasUnknown = /모르겠어요|모르겠습니다/.test(bodyText);
  const pass =
    checks.length === 3
    && checks.every((c) => c.has_arrow && !c.bad_final && !c.skip_leads)
    && !uiHasUnknown;

  const out = {
    pass,
    sid,
    api: API,
    web: WEB,
    evidence_mode: rep.evidence_mode,
    skipped: rep.user_skipped_tasks,
    ui_has_unknown: uiHasUnknown,
    checks,
  };
  const outPath = path.join(ROOT, `.e2e_guidance_v2_${Date.now()}.json`);
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf-8');
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
  process.exit(pass ? 0 : 1);
}

await main();

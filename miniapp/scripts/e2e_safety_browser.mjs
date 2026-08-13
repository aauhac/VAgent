/**
 * Pre-launch browser E2E (Chromium):
 *  - Normal: Safety → Recording Choice → first task
 *  - Pain: pain_on_phonation → SAFETY_LIMITED (no recording task)
 *  - Skip-all: Recording Choice → concern-only report
 *  - Partial: record task1 via FE → skip task2 → PARTIAL_PRECISION report
 *
 * All /v1 traffic is forced to BACKEND (default :8001) so Vite :8000 proxy mismatch cannot occur.
 *
 *   node miniapp/scripts/e2e_safety_browser.mjs
 */
import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const API = process.env.VAGENT_E2E_API || 'http://127.0.0.1:8001';
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
import io, json, struct, time, wave, urllib.request, urllib.error
API = "${API}"; USER = "${USER}"
def wav(seconds=2.5):
    buf=io.BytesIO()
    with wave.open(buf,"wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(44100)
        wf.writeframes(struct.pack("<h", 1200)*int(44100*seconds))
    return buf.getvalue()
def req(method, path, data=None, files=None):
    url=API+path
    headers={"X-User-Id":USER,"X-VAgent-User-Key":USER}
    if files:
        import uuid
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
        with urllib.request.urlopen(r,timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")
st,up=req("POST","/v1/analyses",data={"analysis_mode":"FUNCTIONAL","input_mode":"VOCAL_ONLY","separate":"false"},files={"file":("t.wav",wav(),"audio/wav")})
assert st==200, up
aid=up["analysis_id"]; body=None
for _ in range(160):
    st,body=req("GET",f"/v1/analyses/{aid}")
    if body.get("status")=="completed": break
    time.sleep(0.25)
assert body and body.get("status")=="completed", body
req("POST",f"/v1/analyses/{aid}/mock-unlock-detail")
st,sess=req("POST",f"/v1/diagnostic-sessions?source_analysis_id={aid}"); assert st==200, sess
sid=sess["session_id"]
st,pay=req("POST",f"/v1/diagnostic-sessions/{sid}/mock-pay",data={"product_id":"diagnostic_upgrade"}); assert st==200, pay
st,concerns=req("POST",f"/v1/diagnostic-sessions/{sid}/concerns",data={"diagnostic_mode":"CONCERN_FOCUSED","user_concerns":[{"id":"THROAT_EFFORT"}]})
assert st==200, concerns
print(json.dumps({"session_id":sid,"status":concerns.get("status"),"analysis_id":aid,"api":API}))
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
  const seen = new Set();
  await page.route('**/v1/**', async (route) => {
    const req = route.request();
    const u = new URL(req.url());
    const target = `${API}${u.pathname}${u.search}`;
    seen.add(`${req.method()} ${u.pathname}`);
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
  return seen;
}

async function newPage(browser, wavB64) {
  const page = await browser.newPage();
  const seen = await withApiProxy(page);
  await page.addInitScript(
    ({ user, wavB64: b64 }) => {
      sessionStorage.setItem(
        'vagent_user_identity_v1',
        JSON.stringify({ provider: 'DEV', subject: user }),
      );
      window.__E2E_WAV_B64__ = b64;
      // FE recording path: getUserMedia + MediaRecorder → upload blob
      navigator.mediaDevices.getUserMedia = async () => {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const dst = ctx.createMediaStreamDestination();
        osc.connect(dst);
        osc.start();
        const stream = dst.stream;
        stream._e2eCtx = ctx;
        stream._e2eOsc = osc;
        return stream;
      };
      class E2ERecorder {
        constructor(stream, opts) {
          this.stream = stream;
          this.mimeType = (opts && opts.mimeType) || 'audio/wav';
          this.state = 'inactive';
          this.ondataavailable = null;
          this.onstop = null;
        }
        start() {
          this.state = 'recording';
        }
        stop() {
          this.state = 'inactive';
          const bin = atob(window.__E2E_WAV_B64__);
          const bytes = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
          const blob = new Blob([bytes], { type: 'audio/wav' });
          if (this.ondataavailable) this.ondataavailable({ data: blob });
          try {
            this.stream?._e2eOsc?.stop?.();
            this.stream?._e2eCtx?.close?.();
          } catch (_) {}
          if (this.onstop) this.onstop();
        }
      }
      window.MediaRecorder = E2ERecorder;
      MediaRecorder.isTypeSupported = () => true;
    },
    { user: USER, wavB64 },
  );
  return { page, seen };
}

function trackHome(page, trace) {
  page.on('framenavigated', (frame) => {
    if (frame !== page.mainFrame()) return;
    const p = new URL(frame.url()).pathname;
    if (p === '/' || p === '') {
      trace.went_home = true;
    }
  });
}

async function runNormal(browser, wavB64) {
  const boot = pySession();
  const sid = boot.session_id;
  const trace = { label: 'NORMAL', session_id: sid, went_home: false, api: API, web: WEB };
  const { page, seen } = await newPage(browser, wavB64);
  trackHome(page, trace);
  page.on('response', async (res) => {
    if (res.url().includes(`/diagnostic-sessions/${sid}/safety`) && res.request().method() === 'POST') {
      trace.safety_http = res.status();
      const j = await res.json().catch(() => null);
      if (j) {
        trace.safety_status = j.status;
        trace.selected = j.selected_tasks;
      }
    }
  });
  await page.goto(`${WEB}/diagnostic/${sid}/safety`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: '다음' }).click();
  await page.waitForURL(`**/diagnostic/${sid}/recordings`, { timeout: 20000 });
  trace.route_after_safety = new URL(page.url()).pathname;
  await page.getByRole('button', { name: /추가 녹음 시작/ }).click();
  await page.waitForURL(`**/diagnostic/${sid}/task/**`, { timeout: 20000 });
  trace.route_after_start = new URL(page.url()).pathname;
  await page.waitForSelector('text=녹음 시작', { timeout: 15000 });
  trace.task_visible = (await page.getByRole('button', { name: '녹음 시작' }).count()) > 0;
  trace.v1_calls = [...seen];
  await page.close();
  return {
    pass: !trace.went_home && (trace.route_after_start || '').includes('/task/') && trace.task_visible,
    trace,
  };
}

async function runPain(browser, wavB64) {
  const boot = pySession();
  const sid = boot.session_id;
  const trace = { label: 'PAIN', session_id: sid, went_home: false, api: API, web: WEB };
  const { page, seen } = await newPage(browser, wavB64);
  trackHome(page, trace);
  page.on('response', async (res) => {
    if (res.url().includes(`/diagnostic-sessions/${sid}/safety`) && res.request().method() === 'POST') {
      const j = await res.json().catch(() => null);
      if (j) {
        trace.safety_status = j.status;
        trace.selected = j.selected_tasks;
        trace.diagnostic_status = j.diagnostic_status;
      }
    }
  });
  await page.goto(`${WEB}/diagnostic/${sid}/safety`, { waitUntil: 'networkidle' });
  // First checkbox = pain_on_phonation
  await page.locator('input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: '다음' }).click();
  await page.waitForTimeout(2500);
  trace.route_after_safety = new URL(page.url()).pathname;
  // Must NOT land on a recording task
  const onTask = (trace.route_after_safety || '').includes('/task/');
  const onRecordings = (trace.route_after_safety || '').includes('/recordings');
  // May be analyzing or report
  const limitedUi =
    (await page.locator('text=추가 발성 녹음은 진행하지 않').count()) > 0
    || (await page.locator('text=기존 노래에서 확인된').count()) > 0
    || (trace.route_after_safety || '').includes('/report');
  await page.waitForURL(`**/diagnostic/${sid}/report`, { timeout: 120000 }).catch(() => null);
  trace.route_final = new URL(page.url()).pathname;
  trace.v1_calls = [...seen];
  await page.close();
  const pass =
    !trace.went_home
    && !onTask
    && !onRecordings
    && trace.safety_status === 'READY_FOR_ANALYSIS'
    && Array.isArray(trace.selected)
    && trace.selected.length === 0
    && (limitedUi || (trace.route_final || '').includes('/report'));
  return { pass, trace };
}

async function runSkipAll(browser, wavB64) {
  const boot = pySession();
  const sid = boot.session_id;
  const trace = { label: 'SKIP_ALL', session_id: sid, went_home: false };
  const { page } = await newPage(browser, wavB64);
  trackHome(page, trace);
  await page.goto(`${WEB}/diagnostic/${sid}/safety`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: '다음' }).click();
  await page.waitForURL(`**/diagnostic/${sid}/recordings`, { timeout: 20000 });
  await page.getByRole('button', { name: /추가 녹음 없이 결과 보기/ }).click();
  await page.getByRole('button', { name: /추가 녹음 없이 계속/ }).click();
  await page.waitForURL(`**/diagnostic/${sid}/report`, { timeout: 120000 });
  trace.route = new URL(page.url()).pathname;
  await page.close();
  return { pass: !trace.went_home && trace.route.includes('/report'), trace };
}

async function runPartial(browser, wavB64) {
  const boot = pySession();
  const sid = boot.session_id;
  const trace = {
    label: 'PARTIAL',
    session_id: sid,
    went_home: false,
    api: API,
    web: WEB,
    task1: null,
    task2: null,
  };
  const { page, seen } = await newPage(browser, wavB64);
  trackHome(page, trace);

  await page.goto(`${WEB}/diagnostic/${sid}/safety`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: '다음' }).click();
  await page.waitForURL(`**/diagnostic/${sid}/recordings`, { timeout: 20000 });
  await page.getByRole('button', { name: /추가 녹음 시작/ }).click();
  await page.waitForURL(`**/diagnostic/${sid}/task/**`, { timeout: 20000 });
  trace.task1_route = new URL(page.url()).pathname;
  trace.task1 = trace.task1_route.split('/').pop();

  // Real FE recording path (MediaRecorder overridden to fixture WAV)
  await page.getByRole('button', { name: '녹음 시작' }).click();
  await page.waitForTimeout(1200);
  await page.getByRole('button', { name: '녹음 종료' }).click();
  await page.getByRole('button', { name: /다음 단계|제출하고 결과 보기/ }).click();
  await page.waitForTimeout(3000);
  trace.after_upload = new URL(page.url()).pathname;

  // If still on same task (quality fail), fail clearly
  if (trace.after_upload.includes(`/task/${trace.task1}`)) {
    const failMsg = await page.locator('.fail, .muted').allTextContents();
    trace.upload_error = failMsg.join(' | ').slice(0, 300);
    await page.close();
    return { pass: false, trace };
  }

  // Skip next task (or remaining)
  if ((trace.after_upload || '').includes('/task/')) {
    trace.task2 = trace.after_upload.split('/').pop();
    await page.getByRole('button', { name: /이 과제 건너뛰기/ }).click();
    await page.getByRole('button', { name: /이 과제 건너뛰기|계속|확인/ }).click().catch(async () => {
      // confirm panel may reuse same label
      const buttons = page.getByRole('button');
      const n = await buttons.count();
      for (let i = 0; i < n; i++) {
        const t = await buttons.nth(i).innerText();
        if (/건너뛰|계속/.test(t) && !/남은 과제 없이 결과/.test(t)) {
          await buttons.nth(i).click();
          break;
        }
      }
    });
    await page.waitForTimeout(1500);
  }

  // Skip remaining if more tasks
  if (new URL(page.url()).pathname.includes('/task/')) {
    await page.getByRole('button', { name: /남은 과제 없이 결과 보기/ }).click();
    await page.getByRole('button', { name: /남은 과제 없이 계속/ }).click();
  }

  await page.waitForURL(`**/diagnostic/${sid}/report`, { timeout: 180000 });
  trace.report_route = new URL(page.url()).pathname;

  // Fetch session/report via API for evidence_mode
  const sessRes = await fetch(`${API}/v1/diagnostic-sessions/${sid}`, {
    headers: { 'X-User-Id': USER, 'X-VAgent-User-Key': USER },
  });
  const sess = await sessRes.json();
  trace.evidence_mode = sess.evidence_mode || sess.report?.evidence_mode;
  trace.user_skipped = sess.user_skipped_tasks;
  trace.completed = sess.completed_tasks;
  trace.task_results = (sess.task_results || []).map((t) => t.task_id || t.task);
  // report endpoint
  const repRes = await fetch(`${API}/v1/diagnostic-sessions/${sid}/report`, {
    headers: { 'X-User-Id': USER, 'X-VAgent-User-Key': USER },
  });
  const rep = await repRes.json().catch(() => ({}));
  trace.report_evidence_mode = rep.evidence_mode;
  trace.report_status = repRes.status;
  const bodyText = await page.locator('body').innerText();
  trace.partial_copy =
    /완료한 추가|일부 추가 녹음|확인 범위가 제한/.test(bodyText);
  trace.v1_calls = [...seen];
  await page.close();

  const mode = trace.report_evidence_mode || trace.evidence_mode;
  const completed = trace.completed || [];
  const skipped = trace.user_skipped || [];
  const pass =
    !trace.went_home
    && mode === 'PARTIAL_PRECISION'
    && skipped.length >= 1
    && completed.length >= 1;
  return { pass, trace };
}

// Health check backend
{
  const h = await fetch(`${API}/health`).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  if (h.status !== 'ok') {
    console.error('BACKEND_UNAVAILABLE', API, h);
    process.exit(2);
  }
  console.error('BACKEND_OK', API, 'env=', h.environment);
}

const wavB64 = makeToneWavB64(4.2, 220);
const browser = await chromium.launch({ headless: true });
const results = {
  meta: { api: API, web: WEB, backend_verified: true },
  normal: await runNormal(browser, wavB64),
  pain: await runPain(browser, wavB64),
  skip: await runSkipAll(browser, wavB64),
  partial: await runPartial(browser, wavB64),
};
await browser.close();

const outPath = path.join(ROOT, `.e2e_browser_prelaunch_${Date.now()}.json`);
try {
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf-8');
} catch (e) {
  console.error('WRITE_TRACE_FAILED', String(e));
}
console.log(JSON.stringify(results, null, 2));
const ok =
  results.normal.pass
  && results.pain.pass
  && results.skip.pass
  && results.partial.pass;
process.exit(ok ? 0 : 1);

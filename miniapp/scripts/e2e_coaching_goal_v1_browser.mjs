/**
 * Personalized Coaching Goal v1 — real browser E2E (4 cases).
 *
 *   set VAGENT_E2E_API=http://127.0.0.1:8002
 *   node miniapp/scripts/e2e_coaching_goal_v1_browser.mjs
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

function pyPaidSession() {
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
print(json.dumps({"session_id":sid,"analysis_id":aid}))
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

async function openPage(browser, sid) {
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
  await page.goto(`${WEB}/diagnostic/${sid}/concerns`, { waitUntil: 'networkidle' });
  return page;
}

async function pickConcerns(page, ids) {
  const cats = {
    HIGH_NOTE_CANNOT_REACH: '고음',
    HIGH_NOTE_TOO_EFFORTFUL: '고음',
    HIGH_NOTE_FLIPS: '고음',
    HIGH_NOTE_THINS: '고음',
    TIMBRE_DISSATISFIED: '음색',
    VOICE_TOO_THIN: '음색',
    VOICE_TOO_DARK_MUFFLED: '음색',
  };
  const opened = new Set(['고음']);
  for (const id of ids) {
    const cat = cats[id];
    const row = page.getByTestId(`concern-${id}`);
    if (!(await row.count()) && cat && !opened.has(cat)) {
      await page.locator('.detail-label', { hasText: cat }).first().click();
      opened.add(cat);
    } else if (!(await row.isVisible().catch(() => false)) && cat) {
      await page.locator('.detail-label', { hasText: cat }).first().click();
      opened.add(cat);
    }
    await page.getByTestId(`concern-${id}`).click();
  }
}

async function skipToReport(page, sid) {
  await page.waitForURL(`**/diagnostic/${sid}/safety`, { timeout: 20000 });
  await page.getByRole('button', { name: '다음' }).click();
  await page.waitForURL(`**/diagnostic/${sid}/recordings`, { timeout: 20000 });
  await page.getByRole('button', { name: /추가 녹음 없이 결과 보기/ }).click();
  await page.getByRole('button', { name: /추가 녹음 없이 계속/ }).click();
  await page.waitForURL(`**/diagnostic/${sid}/report`, { timeout: 180000 });
  await page.getByTestId('coaching-goal').waitFor({ timeout: 60000 });
}

async function fetchReport(sid) {
  const repRes = await fetch(`${API}/v1/diagnostic-sessions/${sid}/report`, {
    headers: { 'X-User-Id': USER, 'X-VAgent-User-Key': USER },
  });
  return repRes.json();
}

async function caseA(browser) {
  const boot = pyPaidSession();
  const sid = boot.session_id;
  const page = await openPage(browser, sid);
  await pickConcerns(page, ['TIMBRE_DISSATISFIED', 'VOICE_TOO_THIN', 'VOICE_TOO_DARK_MUFFLED']);
  await page.getByTestId('concern-continue').click();
  await page.getByTestId('timbre-goal-step').waitFor({ timeout: 10000 });
  const genreLabel = await page.getByText('추천 장르').count();
  await page.getByTestId('timbre-option-SOFT_SWEET').click();
  await page.getByTestId('timbre-goal-submit').click();
  await skipToReport(page, sid);
  const body = await page.content();
  const rep = await fetchReport(sid);
  const qs = (rep.personalized_qa && rep.personalized_qa.questions) || [];
  const goal = rep.coaching_goal || {};
  const pass =
    genreLabel === 0
    && (rep.timbre_goal || {}).id === 'SOFT_SWEET'
    && (rep.evidence_mode === 'CONCERN_ONLY' || (rep.completed_tasks || []).length === 0)
    && !body.includes('표준 과제에서 본 결과')
    && body.includes('이번 목표')
    && body.includes('우선 바꿔볼 것')
    && qs.length === 3
    && qs.every((q) => ['TIMBRE_DISSATISFIED', 'VOICE_TOO_THIN', 'VOICE_TOO_DARK_MUFFLED'].includes(q.concern_id))
    && Boolean(goal.goal_title)
    && (!(goal.preserve_labels || []).length || body.includes('유지하면 좋은 점'));
  await page.close();
  return {
    label: 'CASE_A_TIMBRE',
    pass,
    sid,
    evidence_mode: rep.evidence_mode,
    timbre_goal: rep.timbre_goal,
    goal_title: goal.goal_title,
    primary_focus: goal.primary_focus,
    questions: qs.map((q) => q.concern_id),
    genreLabelForbidden: genreLabel === 0,
  };
}

async function caseB(browser) {
  const boot = pyPaidSession();
  const sid = boot.session_id;
  const page = await openPage(browser, sid);
  await pickConcerns(page, ['HIGH_NOTE_CANNOT_REACH', 'HIGH_NOTE_TOO_EFFORTFUL', 'HIGH_NOTE_FLIPS']);
  await page.getByTestId('concern-continue').click();
  const timbreShown = await page.getByTestId('timbre-goal-step').count();
  if (timbreShown) {
    await page.close();
    return { label: 'CASE_B_HIGH_NOTE', pass: false, sid, reason: 'timbre UI shown' };
  }
  await skipToReport(page, sid);
  const body = await page.content();
  const rep = await fetchReport(sid);
  const qs = (rep.personalized_qa && rep.personalized_qa.questions) || [];
  const goal = rep.coaching_goal || {};
  const goalBlocks = await page.getByTestId('coaching-goal').count();
  const pass =
    timbreShown === 0
    && !rep.timbre_goal
    && qs.length === 3
    && goalBlocks === 1
    && Boolean(goal.primary_focus)
    && body.includes('맞춤 연습 방향');
  await page.close();
  return {
    label: 'CASE_B_HIGH_NOTE',
    pass,
    sid,
    questions: qs.map((q) => q.concern_id),
    goal_title: goal.goal_title,
    primary_focus: goal.primary_focus,
    timbreUi: timbreShown,
  };
}

async function caseC(browser) {
  const boot = pyPaidSession();
  const sid = boot.session_id;
  const page = await openPage(browser, sid);
  await pickConcerns(page, ['HIGH_NOTE_THINS', 'TIMBRE_DISSATISFIED']);
  await page.getByTestId('concern-continue').click();
  await page.getByTestId('timbre-goal-step').waitFor({ timeout: 10000 });
  await page.getByTestId('timbre-option-WARM_FULL').click();
  await page.getByTestId('timbre-goal-submit').click();
  await skipToReport(page, sid);
  const body = await page.content();
  const rep = await fetchReport(sid);
  const goal = rep.coaching_goal || {};
  const blob = JSON.stringify(goal);
  const pass =
    (rep.timbre_goal || {}).id === 'WARM_FULL'
    && goal.desired_outcome?.id === 'WARM_FULL'
    && !/성대를/.test(blob)
    && goal.primary_focus !== 'CONTACT'
    && body.includes('이번 목표');
  await page.close();
  return {
    label: 'CASE_C_HIGH_NOTE_TIMBRE',
    pass,
    sid,
    desired: goal.desired_outcome,
    primary_focus: goal.primary_focus,
  };
}

async function caseD(browser) {
  const boot = pyPaidSession();
  const sid = boot.session_id;
  const page = await openPage(browser, sid);
  await pickConcerns(page, ['TIMBRE_DISSATISFIED']);
  await page.getByTestId('concern-continue').click();
  await page.getByTestId('timbre-goal-step').waitFor({ timeout: 10000 });
  await page.getByTestId('timbre-option-RECOMMEND_FOR_ME').click();
  await page.getByTestId('timbre-goal-submit').click();
  await skipToReport(page, sid);
  const rep = await fetchReport(sid);
  const goal = rep.coaching_goal || {};
  const pass =
    (rep.timbre_goal || {}).id === 'RECOMMEND_FOR_ME'
    && goal.desired_outcome?.source === 'SYSTEM_RECOMMENDED'
    && goal.desired_outcome?.id
    && goal.desired_outcome.id !== 'RECOMMEND_FOR_ME'
    && goal.desired_outcome.id !== 'DENSE_SOLID';
  await page.close();
  return {
    label: 'CASE_D_RECOMMEND',
    pass,
    sid,
    stored: rep.timbre_goal,
    recommended: goal.desired_outcome,
  };
}

{
  const h = await fetch(`${API}/health`).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  if (h.status !== 'ok') {
    console.error('BACKEND_UNAVAILABLE', API, h);
    process.exit(2);
  }
}

const browser = await chromium.launch({ headless: true });
const results = {};
try {
  results.CASE_A_TIMBRE = await caseA(browser);
  results.CASE_B_HIGH_NOTE = await caseB(browser);
  results.CASE_C_HIGH_NOTE_TIMBRE = await caseC(browser);
  results.CASE_D_RECOMMEND = await caseD(browser);
} finally {
  await browser.close();
}

const out = {
  meta: { api: API, web: WEB },
  results,
  pass: Object.values(results).every((r) => r.pass),
};
const outPath = path.join(ROOT, `.e2e_coaching_goal_v1_${Date.now()}.json`);
fs.writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf-8');
console.log(JSON.stringify(out, null, 2));
process.exit(out.pass ? 0 : 1);

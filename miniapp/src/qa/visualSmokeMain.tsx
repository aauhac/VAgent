/**
 * QA-only visual smoke entry. Not used by production / build:toss.
 * Serves real React pages with fixture GET responses. Does not unlock paid APIs.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from '../App';
import '../styles/app.css';
import {
  SMOKE_ANALYSIS_ID,
  SMOKE_SESSION_ID,
  analysisAccess,
  detailReport,
  diagnosticProtocol,
  diagnosticSession,
  historyPayload,
  precisionReport,
  productsCatalog,
  progressInsight,
} from './visualSmokeFixtures';

window.addEventListener('error', (ev) => {
  const pre = document.createElement('pre');
  pre.setAttribute('data-visual-error', '1');
  pre.textContent = String(ev.error || ev.message || 'error');
  document.body.prepend(pre);
});
window.addEventListener('unhandledrejection', (ev) => {
  const pre = document.createElement('pre');
  pre.setAttribute('data-visual-error', '1');
  pre.textContent = String(ev.reason || 'rejection');
  document.body.prepend(pre);
});

function silentWav(): Blob {
  const sampleRate = 8000;
  const n = sampleRate; // 1s silence
  const buf = new ArrayBuffer(44 + n * 2);
  const v = new DataView(buf);
  const ascii = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i += 1) v.setUint8(offset + i, s.charCodeAt(i));
  };
  ascii(0, 'RIFF');
  v.setUint32(4, 36 + n * 2, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  ascii(36, 'data');
  v.setUint32(40, n * 2, true);
  return new Blob([buf], { type: 'audio/wav' });
}

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const originalFetch = window.fetch.bind(window);

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url);
  const path = url.replace(/^https?:\/\/[^/]+/, '');

  if (path.includes(`/v1/analyses/${SMOKE_ANALYSIS_ID}/detailed-report`)) return json(detailReport);
  if (path.includes(`/v1/analyses/${SMOKE_ANALYSIS_ID}/access`)) return json(analysisAccess);
  if (path.includes(`/v1/analyses/${SMOKE_ANALYSIS_ID}/preview`) || path.includes(`/v1/analyses/${SMOKE_ANALYSIS_ID}/audio`)) {
    return new Response(silentWav(), { status: 200, headers: { 'Content-Type': 'audio/wav' } });
  }
  if (path.startsWith('/v1/products')) return json(productsCatalog);
  if (path.startsWith('/v1/me/vocal-progress/insight')) return json(progressInsight);
  if (path.startsWith('/v1/me/vocal-goals')) return json({ active: null, history: [] });
  if (path.includes(`/v1/diagnostic-sessions/${SMOKE_SESSION_ID}/report`)) return json(precisionReport);
  if (path.includes(`/v1/diagnostic-sessions/${SMOKE_SESSION_ID}`) && (!init?.method || init.method === 'GET')) {
    return json(diagnosticSession);
  }
  if (path.startsWith('/v1/diagnostic/protocol')) return json(diagnosticProtocol);
  if (path.startsWith('/v1/history')) return json(historyPayload);
  if (path.includes(`/v1/analyses/${SMOKE_ANALYSIS_ID}`) && init?.method === 'DELETE') {
    return json({ deleted: true, analysis_id: SMOKE_ANALYSIS_ID });
  }

  if (path.startsWith('/v1/')) {
    return json({ error: 'VISUAL_SMOKE_UNMOCKED' }, 404);
  }
  return originalFetch(input, init);
};

let hash = window.location.hash || '';
let smokeFlag: string | null = null;
if (hash.startsWith('#smoke-bottom')) {
  smokeFlag = 'bottom';
  hash = `#${hash.slice('#smoke-bottom'.length)}`;
  window.location.hash = hash;
} else if (hash.startsWith('#smoke-delete-confirm')) {
  smokeFlag = 'delete-confirm';
  hash = `#${hash.slice('#smoke-delete-confirm'.length)}`;
  window.location.hash = hash;
} else if (hash.startsWith('#smoke-accordion')) {
  smokeFlag = 'accordion';
  hash = `#${hash.slice('#smoke-accordion'.length)}`;
  window.location.hash = hash;
}

function hashQuery(): URLSearchParams {
  const fromHash = new URLSearchParams();
  if (smokeFlag) fromHash.set('smoke', smokeFlag);
  return fromHash;
}

async function markVisualReady() {
  const q = hashQuery();
  if (q.get('smoke') === 'delete-confirm') {
    const btn = document.querySelector<HTMLButtonElement>('[data-testid="history-delete"]');
    btn?.click();
    await new Promise((r) => window.setTimeout(r, 250));
  }
  if (q.get('smoke') === 'accordion') {
    document.querySelectorAll<HTMLButtonElement>('.accordion-item button').forEach((el, i) => {
      if (i < 2) el.click();
    });
    await new Promise((r) => window.setTimeout(r, 250));
  }
  if (q.get('smoke') === 'bottom') {
    window.scrollTo(0, document.documentElement.scrollHeight);
    await new Promise((r) => window.setTimeout(r, 200));
  }
  document.documentElement.dataset.visualReady = '1';
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>,
);

window.setTimeout(() => {
  void markVisualReady();
}, 1400);

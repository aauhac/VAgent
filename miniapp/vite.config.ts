import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function assertProductionApiBase(mode: string, env: Record<string, string>) {
  const apiBase = (env.VITE_API_BASE || '').trim();
  if (mode !== 'production' || !apiBase) {
    return;
  }
  const lower = apiBase.toLowerCase();
  const banned = ['localhost', '127.0.0.1', 'example.com', '<production_domain>'];
  if (banned.some((token) => lower.includes(token))) {
    throw new Error('VITE_API_BASE must not use a banned host in production builds');
  }
  if (!lower.startsWith('https://')) {
    throw new Error('VITE_API_BASE must be https for production builds');
  }
}

function assertProductionNotificationTemplate(mode: string, env: Record<string, string>) {
  if (mode !== 'production') {
    return;
  }
  const code = (env.VITE_TOSS_ANALYSIS_COMPLETE_TEMPLATE_CODE || '').trim();
  if (!code) {
    throw new Error('PRODUCTION_NOTIFICATION_TEMPLATE_CODE_MISSING');
  }
  const lower = code.toLowerCase();
  const banned = ['test-template', 'sample-template', 'dummy', 'placeholder'];
  if (banned.some((token) => lower.includes(token))) {
    throw new Error('PRODUCTION_NOTIFICATION_TEMPLATE_CODE_INVALID');
  }
}

export default defineConfig(({ mode }) => {
  // Always load from miniapp dir so build cwd / shell env cannot silently drop VITE_* values.
  const env = loadEnv(mode, __dirname, '');
  assertProductionApiBase(mode, env);
  assertProductionNotificationTemplate(mode, env);

  // Default backend is :8000. Tests/E2E may override without editing this file:
  //   VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000';

  return {
    envDir: __dirname,
    plugins: [react()],
    resolve: {
      alias: {
        '@legal': path.resolve(__dirname, '../docs/legal'),
      },
    },
    server: {
      port: 5173,
      host: true,
      fs: { allow: [path.resolve(__dirname, '..')] },
      proxy: {
        '/v1': apiTarget,
        '/health': apiTarget,
      },
    },
  };
});

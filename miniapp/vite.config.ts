import path from 'node:path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

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

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  assertProductionApiBase(mode, env);

  // Default backend is :8000. Tests/E2E may override without editing this file:
  //   VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000';

  return {
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

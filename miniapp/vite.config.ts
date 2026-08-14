import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Default backend is :8000. Tests/E2E may override without editing this file:
//   VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/v1': apiTarget,
      '/health': apiTarget,
    },
  },
});

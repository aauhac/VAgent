/**
 * Apps in Toss granite config (SDK 2.x).
 *
 * Official pattern:
 *   import { defineConfig } from '@apps-in-toss/web-framework/config'
 *
 * icon: leave empty until console upload URL is available (do not invent a URL).
 * Docs: https://developers-apps-in-toss.toss.im/ai-vibe-coding/tutorials/webview.md
 */
import { defineConfig } from '@apps-in-toss/web-framework/config';

export default defineConfig({
  appName: 'vocalfb',
  brand: {
    displayName: '노래 실력 진단받기',
    primaryColor: '#3182F6',
    icon: 'https://static.toss.im/appsintoss/72229/8fece2a9-b7a6-4c8b-b5c9-36cd8d46d883.png',
  },
  web: {
    host: 'localhost',
    port: 5173,
    commands: {
      dev: 'vite',
      build: 'vite build',
    },
  },
  navigationBar: {
    theme: 'light',
  },
  permissions: [{ name: 'microphone', access: 'access' }],
  outdir: 'dist',
});

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
    // TODO: paste icon URL from Apps in Toss console after upload
    icon: '',
  },
  web: {
    host: 'localhost',
    port: 5173,
    commands: {
      dev: 'vite',
      build: 'vite build',
    },
  },
  permissions: [],
  outdir: 'dist',
});

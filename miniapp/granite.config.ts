/**
 * Apps in Toss granite config.
 * Install official SDK when packaging for Toss:
 *   npm install @apps-in-toss/web-framework
 *   npx ait init
 *
 * appName MUST be: vocalfb
 *
 * Docs: https://developers-apps-in-toss.toss.im/ai-vibe-coding/tutorials/webview.md
 */
export default {
  appName: 'vocalfb',
  brand: {
    displayName: '노래 실력 진단받기',
    primaryColor: '#3182F6',
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
  permissions: [] as string[],
  outdir: 'dist',
};

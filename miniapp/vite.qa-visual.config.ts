import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@legal': path.resolve(__dirname, '../docs/legal'),
    },
  },
  server: {
    port: 5177,
    host: true,
    strictPort: true,
    fs: { allow: [path.resolve(__dirname, '..')] },
  },
  build: {
    outDir: 'dist-qa-visual',
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'qa-visual.html'),
    },
  },
});

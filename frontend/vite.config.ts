import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// API and WebSocket calls go to the backend. During frontend work run the mock server:
//   sonarsentinel serve --mock --port 8001
const backend = process.env.SONARSENTINEL_API ?? 'http://127.0.0.1:8001';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
  },
});

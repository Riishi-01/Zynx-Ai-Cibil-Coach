/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
    // jsdom throws SecurityError on localStorage when the origin is opaque;
    // anchor every test window to http://localhost/ so storage is reachable.
    environmentOptions: {
      jsdom: { url: 'http://localhost/' },
    },
  },
});

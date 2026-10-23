import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({ plugins: [react(), tailwindcss()], server: { proxy: { '/api': { target: process.env.API_PROXY_TARGET || 'http://localhost:8000', changeOrigin: true } } }, test: { environment: 'jsdom', setupFiles: ['./tests/setup.ts'], exclude: ['**/node_modules/**','**/e2e.spec.ts'] } });

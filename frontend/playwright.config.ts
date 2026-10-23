import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  workers: 1,
  use: {baseURL: process.env.E2E_BASE_URL || 'http://localhost:8080', viewport: {width: 1440, height: 1000}, trace: 'retain-on-failure'},
  reporter: [['list'], ['html', {open: 'never'}]],
});

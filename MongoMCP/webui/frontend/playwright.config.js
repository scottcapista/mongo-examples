import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:8001',
    headless: true,
  },
  webServer: process.env.PLAYWRIGHT_SKIP_WEBSERVER
    ? undefined
    : {
        command: 'cd .. && python app.py',
        url: 'http://localhost:8001',
        reuseExistingServer: true,
        timeout: 120_000,
      },
})

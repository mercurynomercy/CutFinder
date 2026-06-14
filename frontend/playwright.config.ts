import { defineConfig, devices } from 'playwright/test'

/** See https://playwright.dev/docs/configuration */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',

  use: {
    baseURL: 'http://localhost:5080',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Start the Vite dev server before running e2e tests.
  webServer: {
    command: 'npm run dev -- --port 5080',
    url: 'http://localhost:5080',
    reuseExistingServer: true,
  },
})

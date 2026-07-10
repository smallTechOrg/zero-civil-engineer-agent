import { defineConfig, devices } from '@playwright/test'

// The webServer command is exactly the documented run command; it serves the
// built frontend at /app and the API at /api on a single origin. Real Gemini
// runs take 30–90 s, hence the generous test timeout.
//
// Port parameterization: the phase gate boots its own isolated server on port
// 8004 (E2E_PORT=8004) so it never collides with a presenter's live server on
// 8001. The default is 8004 (NOT 8001) so a bare `npx playwright test` also runs
// against an owned instance; set E2E_PORT to pin any other port.
const port = process.env.E2E_PORT ?? '8004'

export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 240_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: `http://localhost:${port}`,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'uv run python -m src',
    url: `http://localhost:${port}/health`,
    timeout: 90_000,
    // Only reuse a running server on the default port; a gate run on E2E_PORT
    // must boot (and own) its own instance.
    reuseExistingServer: process.env.E2E_PORT === undefined,
    env: { ...(process.env as Record<string, string>), AGENT_PORT: port },
  },
})

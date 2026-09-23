import {defineConfig} from '@playwright/test'

/* Playwright E2E for gammamarkets (02-04 verification).
 *
 * Requires the seeded host server:
 *   uv run python tools/e2e_server.py   # serves http://127.0.0.1:5099
 * then:
 *   cd tests/e2e && npx playwright test
 *
 * The server writes .seed.json (account token, product URLs, seeded
 * order) which the specs read — no credentials are hardcoded. */

const baseURL = process.env.GM_E2E_BASE_URL ?? 'https://localhost:5099'

export default defineConfig({
  testDir: __dirname,
  testMatch: '**/*.spec.ts',
  outputDir: 'test-results',
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  expect: {timeout: 15_000},
  reporter: [['list'], ['html', {open: 'never'}]],
  use: {
    baseURL,
    browserName: 'chromium',
    headless: true,
    viewport: {width: 1280, height: 900},
    ignoreHTTPSErrors: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure'
  }
})

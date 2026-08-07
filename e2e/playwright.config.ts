/**
 * Playwright runner configuration for the Code Skeptic Scanner end-to-end layer.
 *
 * Runs the specs in `e2e/tests` against the self-contained Vite harness declared
 * by `e2e/vite.harness.config.ts`, which the `webServer` block below starts before
 * the first spec and stops after the last one. Nothing here starts a backend
 * process, reads a credential or opens a socket of its own: each spec supplies its
 * own `page.route` interception, and no file under `frontend/` or `backend/` is
 * written by anything configured here.
 *
 * Both documented invocations are supported and resolve to identical absolute
 * paths:
 *
 *   cd e2e && npx playwright test
 *   npx playwright test --config e2e/playwright.config.ts   (repository root)
 *
 * Artifacts written, all three matched by the repository `.gitignore`:
 *
 *   e2e/playwright-report/index.html   HTML report, opened by `npm run report`
 *   e2e/reports/e2e-junit.xml          JUnit XML result stream
 *   e2e/test-results/                  traces, failure screenshots, video
 *
 * Prerequisite: `npx playwright install --with-deps chromium`. See `e2e/README.md`.
 */

import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

/* -------------------------------------------------------------------------- */
/* Paths                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Base for every path in this file. Nothing below reads `process.cwd()`, so the
 * working directory a run is launched from does not change where specs are found
 * or where artifacts land.
 *
 * `e2e/package.json` declares no `"type"` field, so this module is loaded as
 * CommonJS and `__dirname` is defined.
 */
const HERE = __dirname;

/** Spec directory. */
const TESTS_DIR = path.join(HERE, 'tests');

/** Per-test artifact directory: traces, failure screenshots and video. */
const OUTPUT_DIR = path.join(HERE, 'test-results');

/** HTML report directory; `index.html` inside it is the report entry. */
const HTML_REPORT_DIR = path.join(HERE, 'playwright-report');

/** JUnit XML result stream. Its parent directory is created by the reporter. */
const JUNIT_OUTPUT_FILE = path.join(HERE, 'reports', 'e2e-junit.xml');

/* -------------------------------------------------------------------------- */
/* Harness server                                                             */
/* -------------------------------------------------------------------------- */

/**
 * Origin the harness binds, taken from `server.host` and `server.port` in
 * `e2e/vite.harness.config.ts`, which also sets `strictPort: true`: on a port
 * collision the harness fails to start and does not move to another port.
 */
const HARNESS_ORIGIN = 'http://127.0.0.1:4173';

/**
 * Dev-server command. Run with `cwd` set to this directory, which is what lets the
 * relative `--config` argument resolve inside `e2e/` under either invocation.
 *
 * `e2e/vite.harness.config.ts` configures the dev server only and declares no
 * `build` options.
 */
const HARNESS_COMMAND = 'npx vite --config vite.harness.config.ts';

/** Start budget for the harness, which pre-bundles `optimizeDeps` on a cold run. */
const HARNESS_START_TIMEOUT_MS = 120_000;

/* -------------------------------------------------------------------------- */
/* Environment                                                               */
/* -------------------------------------------------------------------------- */

/**
 * Set by GitHub Actions and by CI providers generally, and unset on a developer
 * machine. Selects the local branch of each setting keyed off it below, so a clean
 * checkout runs the suite with no environment variable configured at all.
 */
const IS_CI = Boolean(process.env.CI);

/* -------------------------------------------------------------------------- */
/* Configuration                                                              */
/* -------------------------------------------------------------------------- */

export default defineConfig({
  testDir: TESTS_DIR,
  testMatch: '**/*.spec.ts',

  // Per-test and per-assertion budgets.
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },

  // Files and tests run concurrently. Each spec installs its own route
  // interception and shares no state with any other spec.
  fullyParallel: true,

  // Under CI, a committed `test.only` fails the run.
  forbidOnly: IS_CI,

  // A retry is what produces a trace, per `use.trace` below.
  retries: IS_CI ? 2 : 0,

  // One worker under CI; locally Playwright derives the count from the host.
  workers: IS_CI ? 1 : undefined,

  outputDir: OUTPUT_DIR,

  reporter: [
    // Local dashboard. `open: 'never'` suppresses the default `'on-failure'`
    // behaviour, which spawns a browser and blocks a non-interactive run.
    ['html', { outputFolder: HTML_REPORT_DIR, open: 'never' }],

    // Machine-readable result stream. Each `<testcase>` carries the spec file and
    // the test title, which is what ties a result back to its source.
    ['junit', { outputFile: JUNIT_OUTPUT_FILE }],
  ],

  use: {
    // Specs navigate with bare paths, for example `await page.goto('/tweets')`.
    baseURL: HARNESS_ORIGIN,

    // Evidence captured across the browser/API boundary. The trace records every
    // intercepted request with its timing; the screenshot and video are kept only
    // for a test that fails.
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',

    // Fixed viewport, clock offset and locale, so rendered output and any
    // date-formatted text do not vary with the host running the suite.
    viewport: { width: 1280, height: 720 },
    timezoneId: 'UTC',
    locale: 'en-US',
  },

  // One project. The CI job installs the chromium browser only.
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: HARNESS_COMMAND,
    cwd: HERE,

    // Polled until it answers, which gates the first spec.
    url: `${HARNESS_ORIGIN}/`,

    // Locally an already-running harness is reused; under CI the run owns the
    // server it starts.
    reuseExistingServer: !IS_CI,
    timeout: HARNESS_START_TIMEOUT_MS,

    // The dev-server log is the harness's health signal; piping both streams puts
    // it in the run's output.
    stdout: 'pipe',
    stderr: 'pipe',
  },
});

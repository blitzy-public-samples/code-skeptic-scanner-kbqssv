/**
 * Playwright runner configuration for the Code Skeptic Scanner end-to-end layer.
 *
 * Runs the specs under `e2e/tests` against the self-contained Vite harness declared
 * by `e2e/vite.harness.config.ts`, which the `webServer` block below starts on a
 * loopback origin before the first spec and stops after the last one. That harness
 * server is the only process started here: no backend runs, no credential is read,
 * and each spec supplies its own `page.route` interception.
 *
 * Host, port and origin come from `./harness-origin`, which the Vite config and
 * `e2e/tests/harness-fixtures.ts` read as well, so nothing here computes an origin of
 * its own.
 *
 * The runner is owned by `e2e/package.json`, which pins `@playwright/test` at 1.44.1.
 * Every invocation must resolve the binary through that package, and every path in
 * this file comes from `__dirname` rather than the working directory, so all four of
 * these resolve identically:
 *
 *   cd e2e && npx playwright test                 inside this package
 *   npm --prefix e2e test                         from the repository root
 *   npm run test:e2e                              from `frontend/`
 *   npx playwright test                           in CI, `working-directory: e2e`
 *
 * `npx playwright test --config e2e/playwright.config.ts` from the repository root is
 * NOT one of them: it resolves no project-owned runner. Use one of the four above.
 *
 * Configured output paths, all three matched by the repository `.gitignore`:
 *
 *   e2e/playwright-report/index.html   HTML report, opened by `npm --prefix e2e run report`
 *   e2e/reports/e2e-junit.xml          JUnit XML result stream
 *   e2e/test-results/                  traces, failure screenshots, video
 *
 * Prerequisite: a Chromium build already present in Playwright's cache, or one named
 * by `PLAYWRIGHT_CHROMIUM_EXECUTABLE`. `npm --prefix e2e run browsers:verify` reports
 * what the runner needs without fetching anything. See `e2e/README.md`.
 *
 * @see docs/testing/DECISION-LOG.md - section 4 and rows D111, D114, D128, D129.
 */

import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

import { HARNESS_HOST, HARNESS_ORIGIN, HARNESS_PORT } from './harness-origin';

/* -------------------------------------------------------------------------- */
/* Paths                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Base for every path in this file; nothing below reads `process.cwd()`.
 * `e2e/package.json` declares no `"type"` field, so this module loads as CommonJS
 * and `__dirname` is defined.
 */
const HERE = __dirname;

const TESTS_DIR = path.join(HERE, 'tests');

const OUTPUT_DIR = path.join(HERE, 'test-results');

const HTML_REPORT_DIR = path.join(HERE, 'playwright-report');

const JUNIT_OUTPUT_FILE = path.join(HERE, 'reports', 'e2e-junit.xml');

/* Harness server. */

/**
 * Dev-server command, run with `cwd` set to this directory.
 *
 * Names the pinned local binary rather than going through `npx`, which resolves from
 * the registry when the local executable is missing. The port is passed explicitly
 * even though the config resolves the same value from `./harness-origin`, so a
 * collision is diagnosable from the process command line, and `--strictPort` fails
 * the start rather than moving to another port.
 *
 * @see docs/testing/DECISION-LOG.md - row D123.
 */
const HARNESS_COMMAND =
  `node ./node_modules/vite/bin/vite.js --config vite.harness.config.ts` +
  ` --port ${HARNESS_PORT} --strictPort`;

const HARNESS_START_TIMEOUT_MS = 120_000;

/** Closed loopback port every request that is not bypassed is routed at. */
const CLOSED_PROXY_ORIGIN = 'http://127.0.0.1:1';

/**
 * Chromium switches that deny network egress below the route layer, so a Service
 * Worker request, a popup's first request and a spec that installed no route are all
 * covered.
 *
 * Invariants:
 *
 * - no hostname resolves except {@link HARNESS_HOST};
 * - every request that is not bypassed is routed at {@link CLOSED_PROXY_ORIGIN};
 * - exactly one origin is bypassed, `HARNESS_HOST:HARNESS_PORT`. `<-loopback>`
 *   subtracts Chromium's implicit bypass of all loopback and link-local addresses,
 *   without which every other service on this host would stay directly reachable.
 *
 * @see docs/testing/DECISION-LOG.md - rows D114 and D128.
 */
const NO_EGRESS_BROWSER_ARGS = [
  `--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE ${HARNESS_HOST}`,
  `--proxy-server=${CLOSED_PROXY_ORIGIN}`,
  `--proxy-bypass-list=<-loopback>;${HARNESS_HOST}:${HARNESS_PORT}`,
];

/**
 * Optional path to a pre-verified Chromium executable.
 *
 * Left unset, Playwright uses the build already in its own cache. No automated path
 * in this package downloads a browser: the pinned `@playwright/test` 1.44.1 is
 * affected by CVE-2025-59288, whose remedy taken here is to provision only from
 * artifacts verified out of band.
 *
 * @see docs/testing/DECISION-LOG.md - rows D111 and D129.
 */
const CHROMIUM_EXECUTABLE = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;

/* -------------------------------------------------------------------------- */
/* Environment                                                               */
/* -------------------------------------------------------------------------- */

/** Set by CI providers. Selects the CI branch of each setting keyed off it. */
const IS_CI = Boolean(process.env.CI);

export default defineConfig({
  testDir: TESTS_DIR,
  testMatch: '**/*.spec.ts',

  // Per-test and per-assertion budgets.
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },

  // Files and tests run concurrently; specs share no state.
  fullyParallel: true,

  // Under CI, a committed `test.only` fails the run.
  forbidOnly: IS_CI,

  // Retries are a CI-only allowance for infrastructure flake; a local run reports
  // the first outcome. Tracing does not depend on a retry - see `use.trace` below.
  retries: IS_CI ? 2 : 0,

  // One worker under CI; locally Playwright derives the count from the host.
  workers: IS_CI ? 1 : undefined,

  outputDir: OUTPUT_DIR,

  reporter: [
    // Local dashboard. `open: 'never'` keeps a non-interactive run from spawning a
    // browser and blocking on it.
    ['html', { outputFolder: HTML_REPORT_DIR, open: 'never' }],

    // Machine-readable result stream. Each `<testcase>` carries the spec file and
    // the test title, which is what ties a result back to its source and to the
    // trace directory named after it.
    ['junit', { outputFile: JUNIT_OUTPUT_FILE }],
  ],

  use: {
    baseURL: HARNESS_ORIGIN,

    // Evidence across the browser/API boundary, for every failing test on its first
    // attempt, locally as well as under CI. The trace records each intercepted
    // request with its timing and carries the test title, which ties
    // `e2e/test-results/` back to a `<testcase>` in the JUnit stream.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',

    // Fixed viewport, timezone and locale, so rendered output and any date-formatted
    // text do not vary with the host running the suite.
    viewport: { width: 1280, height: 720 },
    timezoneId: 'UTC',
    locale: 'en-US',

    // No Service Worker may register: `page.route` does not intercept a worker's
    // requests, and the harness registers none.
    serviceWorkers: 'block',

    // Browser-level egress denial, below every route handler; see
    // NO_EGRESS_BROWSER_ARGS. `e2e/tests/harness-fixtures.ts` adds the mandatory
    // context-wide rule on top, which is what attributes a refusal to a test.
    launchOptions: {
      args: NO_EGRESS_BROWSER_ARGS,
      ...(CHROMIUM_EXECUTABLE === undefined ? {} : { executablePath: CHROMIUM_EXECUTABLE }),
    },
  },

  // One project; chromium is the only browser this layer requires.
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: HARNESS_COMMAND,
    cwd: HERE,

    // Binds the port this file polls, whatever CLONE_INDEX the child process would
    // otherwise have read.
    env: { E2E_PORT: String(HARNESS_PORT) },

    // Polled until it answers, which gates the first spec.
    url: `${HARNESS_ORIGIN}/`,

    // Never reuse: `reuseExistingServer` cannot tell this harness from a stale one,
    // an unrelated local server, or another user's process on a shared host, and each
    // of those would silently become the subject under test. With `strictPort: true`
    // in the harness config a held port fails the run instead of moving elsewhere.
    //
    // @see docs/testing/DECISION-LOG.md - row D112.
    reuseExistingServer: false,
    timeout: HARNESS_START_TIMEOUT_MS,

    // The dev-server log is the harness's health signal, and it carries the
    // `harness-api-not-intercepted` lines; piping both streams puts them in the run's
    // output.
    stdout: 'pipe',
    stderr: 'pipe',
  },
});

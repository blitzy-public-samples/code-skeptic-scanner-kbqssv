/**
 * Playwright runner configuration for the Code Skeptic Scanner end-to-end layer.
 *
 * Runs the specs under `e2e/tests` against the self-contained Vite harness
 * declared by `e2e/vite.harness.config.ts`, which the `webServer` block below
 * starts on a loopback origin before the first spec and stops after the last one.
 * That harness server is the only process started here: no backend runs, no
 * credential is read, and each spec supplies its own `page.route` interception.
 *
 * The runner is owned by `e2e/package.json`, which pins `@playwright/test` at
 * 1.44.1, so every invocation has to resolve the binary through that package.
 * These do, and each resolves to the same absolute paths because every path in
 * this file comes from `__dirname` rather than the working directory:
 *
 *   cd e2e && npx playwright test                 inside this package
 *   npm --prefix e2e test                         from the repository root
 *   npm run test:e2e                              from `frontend/`, which
 *                                                 delegates with `--prefix ../e2e`
 *   npx playwright test                           in CI, with the step's
 *                                                 `working-directory: e2e`
 *
 * `npx playwright test --config e2e/playwright.config.ts` from the repository
 * root is NOT one of them: npm's `npx` searches the working directory and its
 * ancestors for `node_modules/.bin`, never a child package's, so at the root it
 * finds no project-owned runner and falls back to whatever `npx` has cached or
 * can fetch from the registry - a floating version rather than the pinned one,
 * and a network dependency on a machine with a cold cache. Use one of the four
 * commands above in documentation, scripts and CI.
 *
 * Configured output paths, all three matched by the repository `.gitignore`:
 *
 *   e2e/playwright-report/index.html   HTML report, opened by `npm --prefix e2e run report`
 *   e2e/reports/e2e-junit.xml          JUnit XML result stream
 *   e2e/test-results/                  traces, failure screenshots, video
 *
 * Prerequisite, and package-owned for the same reason: the browser download,
 * `npm run install:browsers` inside `e2e/` or `npm --prefix e2e run
 * install:browsers` from the repository root. See `e2e/README.md`.
 */

import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

import { HARNESS_ORIGIN, HARNESS_PORT } from './harness-origin';

/* -------------------------------------------------------------------------- */
/* Paths                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Base for every path in this file; nothing below reads `process.cwd()`, so the
 * directory a run is launched from changes nothing. `e2e/package.json` declares
 * no `"type"` field, so this module loads as CommonJS and `__dirname` is defined.
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
 * The pinned local binary is invoked directly rather than through `npx`. `npx` is
 * online-capable: when the local executable is missing it resolves the package
 * from the registry and runs whatever it downloads, which is a silent
 * substitution of an unpinned, unverified `vite` for the pinned one. Naming
 * `node_modules/vite/bin/vite.js` fails closed instead — an absent dependency is
 * a `MODULE_NOT_FOUND`, not a download.
 *
 * `e2e/vite.harness.config.ts` configures the dev server only and declares no
 * `build` options.
 *
 * The port is passed explicitly even though `e2e/vite.harness.config.ts` resolves the
 * same value from the same `./harness-origin` module: it puts the port on the process
 * command line, where a collision is diagnosable. `--strictPort` fails the start on a
 * collision rather than moving to another port.
 */
const HARNESS_COMMAND =
  `node ./node_modules/vite/bin/vite.js --config vite.harness.config.ts` +
  ` --port ${HARNESS_PORT} --strictPort`;

const HARNESS_START_TIMEOUT_MS = 120_000;

/**
 * Chromium switches that deny network egress at the browser, not at the page.
 *
 * `page.route` and `browserContext.route` are the documented interception points,
 * but Playwright records that page routes do not see a Service Worker's requests
 * or a popup's very first request, and a spec that forgets to install one sees
 * nothing at all. These switches sit below every one of those cases:
 *
 * - `--host-resolver-rules` fails every DNS lookup except the literal loopback
 *   address, so no hostname resolves;
 * - `--proxy-server` points every remaining request at a closed loopback port,
 *   which covers a request to a literal external IP that needs no lookup, while
 *   `--proxy-bypass-list` keeps the harness itself direct.
 *
 * The harness is served from `127.0.0.1:4173`, so nothing the suite legitimately
 * needs is affected.
 */
const NO_EGRESS_BROWSER_ARGS = [
  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
  '--proxy-server=http://127.0.0.1:1',
  '--proxy-bypass-list=127.0.0.1;localhost',
];

/**
 * Optional path to a pre-verified Chromium executable.
 *
 * The pinned `@playwright/test` 1.44.1 is affected by CVE-2025-59288: its browser
 * downloader does not verify the TLS certificate chain of the host it fetches
 * from. The remedy taken here is the advisory's other one — provision from
 * artifacts that were verified out of band, never from a download during a test
 * run. `npm run browsers:verify` reports what the runner needs without fetching
 * anything, and this variable pins the binary explicitly where an operator wants
 * to be certain which one is used. Left unset, Playwright uses its own verified
 * cache. Upgrading to `>=1.55.1` would require Node >= 18, which the AAP's CI
 * matrix does not run; see `docs/testing/DECISION-LOG.md`.
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

    // Evidence captured across the browser/API boundary, for every failing test on
    // its first attempt, locally as well as under CI. The trace records each
    // intercepted request with its timing and carries the test title, which is what
    // ties `e2e/test-results/` back to a `<testcase>` in the JUnit stream.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',

    // Fixed viewport, clock offset and locale, so rendered output and any
    // date-formatted text do not vary with the host running the suite.
    viewport: { width: 1280, height: 720 },
    timezoneId: 'UTC',
    locale: 'en-US',

    // No Service Worker may register. Playwright documents that `page.route` does
    // not intercept a Service Worker's requests, so a worker is a route the
    // suite cannot see; the harness registers none, so blocking them removes the
    // hole at no cost.
    serviceWorkers: 'block',

    // Browser-level egress denial, below every route handler; see
    // NO_EGRESS_BROWSER_ARGS. `e2e/tests/harness-fixtures.ts` adds the
    // context-wide abort rule on top, so a request is refused by the browser and
    // attributed by the fixture.
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

    // Binds the port this file polls, whatever CLONE_INDEX the child process
    // would otherwise have read.
    env: { E2E_PORT: String(HARNESS_PORT) },

    // Polled until it answers, which gates the first spec.
    url: `${HARNESS_ORIGIN}/`,

    // Never reuse. `reuseExistingServer` decides only whether *something* already
    // answers on the port; it cannot tell the harness from an unrelated process,
    // a stale harness started from a different checkout, or a server another user
    // on the host put there. Every one of those would be accepted as the subject
    // under test, and a spec's assertions would then describe content this
    // configuration did not produce. Owning the server on every run costs a
    // sub-second start — `strictPort: true` in the harness config means a port
    // collision fails the run instead of silently moving elsewhere.
    reuseExistingServer: false,
    timeout: HARNESS_START_TIMEOUT_MS,

    // The dev-server log is the harness's health signal; piping both streams puts
    // it in the run's output.
    stdout: 'pipe',
    stderr: 'pipe',
  },
});

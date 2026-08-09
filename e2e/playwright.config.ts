/**
 * Playwright runner configuration for the Code Skeptic Scanner end-to-end layer.
 *
 * Runs the specs under `e2e/tests` against the self-contained Vite harness declared
 * by `e2e/vite.harness.config.ts`, which the `webServer` block below starts on a
 * loopback origin before the first spec and stops after the last one. That harness
 * server is the only process started here: no backend runs, no credential is read,
 * and each spec supplies its own `page.route` interception.
 *
 * Host, port and origin come from `./vite.harness.config`, the file that binds the
 * socket, so nothing here computes an origin of its own.
 *
 * This file declares no fixtures. The `test` and `expect` every spec imports, and the
 * `noEgress` and `browserDiagnostics` fixtures that complete them, live in
 * `./tests/harness-fixtures.ts`, and a spec reaches them by importing
 * `'./harness-fixtures'`. What this file re-exports is {@link HARNESS_ORIGIN} alone, so a
 * spec can anchor a route pattern without importing the Vite config directly. `testMatch`
 * below is the recursive `.spec.ts` glob under `testDir`; `harness-fixtures.ts` sits inside
 * that directory but does not match the glob, and this file sits outside it, so neither is
 * ever collected as a spec.
 *
 * The runner is owned by `e2e/package.json`, which pins `@playwright/test` at 1.44.1.
 * Every invocation must resolve the binary through that package, and every path in this
 * file comes from `__dirname` rather than the working directory, so all three of these
 * resolve identically:
 *
 *   cd e2e && npm test                            inside this package, and in CI
 *   npm --prefix e2e test                         from the repository root
 *   npm run test:e2e                              from `frontend/`
 *
 * `.github/workflows/ci.yml` uses the first, with `working-directory: e2e`. A package
 * script runs the binary from this package's own `node_modules/.bin` and cannot fall back
 * to the registry, which is why every form above is spelled as one.
 *
 * `npx playwright test --config e2e/playwright.config.ts` from the repository root is
 * NOT one of them: it resolves no project-owned runner and must not be used. Use one of
 * the three above. See docs/testing/DECISION-LOG.md rows D49, D197 and D237.
 *
 * Configured output paths, all three matched by the repository `.gitignore`:
 *
 *   e2e/playwright-report/index.html   HTML report, opened by `npm --prefix e2e run report`
 *   e2e/reports/e2e-junit.xml          JUnit XML result stream
 *   e2e/test-results/                  traces, failure screenshots, video
 *
 * Prerequisite: a Chromium build already present in Playwright's cache, or one named
 * by `PLAYWRIGHT_CHROMIUM_EXECUTABLE`. `npm --prefix e2e run browsers:verify` fetches
 * nothing and exits non-zero when neither route holds a launchable executable. See
 * `e2e/README.md`.
 *
 * @see docs/testing/DECISION-LOG.md - section 4 and rows D111, D114, D128, D129, D347.
 */

import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

import { HARNESS_HOST, HARNESS_ORIGIN, HARNESS_PORT } from './vite.harness.config';

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
 * Names the pinned local binary, not `npx`, which resolves from the registry when the
 * local executable is missing. The port is passed explicitly as well as resolved from
 * `./vite.harness.config`, so a collision is diagnosable from the process command line,
 * and `--strictPort` fails the start on a held port rather than moving port.
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
 *   subtracts Chromium's implicit bypass of all loopback and link-local addresses, so
 *   no other service on this host is directly reachable.
 *
 * @see docs/testing/DECISION-LOG.md - rows D114 and D128.
 */
const NO_EGRESS_BROWSER_ARGS = [
  `--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE ${HARNESS_HOST}`,
  `--proxy-server=${CLOSED_PROXY_ORIGIN}`,
  `--proxy-bypass-list=<-loopback>;${HARNESS_HOST}:${HARNESS_PORT}`,
];

/**
 * Reads an optional filesystem path from the environment.
 *
 * An unset variable and one holding only whitespace are the same answer: no path was
 * supplied. Both occur: `.github/workflows/ci.yml` passes the value through a GitHub
 * Actions configuration variable, and an Actions expression whose variable is not
 * defined expands to the **empty string** while leaving the variable in the
 * environment. An empty `executablePath` fails a launch; `undefined` falls back to the
 * Playwright cache.
 *
 * @param name - Variable to read.
 * @returns The trimmed value, or `undefined` when the variable is unset or blank.
 */
function readOptionalPath(name: string): string | undefined {
  const raw = process.env[name];
  if (raw === undefined) {
    return undefined;
  }

  const trimmed = raw.trim();
  return trimmed === '' ? undefined : trimmed;
}

/**
 * Optional path to a pre-verified Chromium executable.
 *
 * Left unset - or set to a blank value, which is what an undefined CI variable produces -
 * Playwright uses the build already in its own cache. No automated path in this package
 * downloads a browser, because the pinned `@playwright/test` 1.44.1 is affected by
 * CVE-2025-59288: provisioning is from out-of-band verified artifacts only.
 * `scripts/verify-browser.js` fetches nothing and refuses a run when neither this
 * variable nor the cache holds a launchable build.
 *
 * @see docs/testing/DECISION-LOG.md - rows D111, D129 and D236.
 */
const CHROMIUM_EXECUTABLE = readOptionalPath('PLAYWRIGHT_CHROMIUM_EXECUTABLE');

/**
 * Optional SHA-256 that {@link CHROMIUM_EXECUTABLE} must still hash to.
 *
 * Published by `scripts/require-browser.js`, which computes it from the file it validated. Set,
 * this closes the gap between that validation and the launch below: without it the gate and the
 * launcher share only a path, and a path is a mutable pointer - a symlink can be repointed and a
 * user-writable binary replaced in the interval, leaving the run to launch something no gate ever
 * inspected.
 *
 * @see docs/testing/DECISION-LOG.md - row D319.
 */
const CHROMIUM_EXECUTABLE_DIGEST = readOptionalPath('PLAYWRIGHT_CHROMIUM_EXECUTABLE_SHA256');

/**
 * Re-hashes {@link CHROMIUM_EXECUTABLE} and throws when it no longer matches
 * {@link CHROMIUM_EXECUTABLE_DIGEST}.
 *
 * Runs at configuration load, which is the latest point this file controls and the closest one to
 * the launch - the runner reads this module, and so does every worker that launches a browser.
 * Costs a single file hash, and only when a digest was published: a local run that set only the
 * path pays nothing and is told, once, that it is unbound.
 *
 * Throwing is deliberate. A provenance mismatch means the browser about to run is not the browser
 * that was checked, which is not a condition to report and continue through.
 *
 * @returns The executable path, unchanged, so this can guard the value at its point of use.
 */
function verifiedExecutable(): string | undefined {
  if (CHROMIUM_EXECUTABLE === undefined || CHROMIUM_EXECUTABLE_DIGEST === undefined) {
    return CHROMIUM_EXECUTABLE;
  }

  const actual = createHash('sha256').update(readFileSync(CHROMIUM_EXECUTABLE)).digest('hex');
  if (actual !== CHROMIUM_EXECUTABLE_DIGEST.toLowerCase()) {
    throw new Error(
      [
        'The browser named by PLAYWRIGHT_CHROMIUM_EXECUTABLE is not the one that was validated.',
        `  path:     ${CHROMIUM_EXECUTABLE}`,
        `  expected: ${CHROMIUM_EXECUTABLE_DIGEST.toLowerCase()}`,
        `  actual:   ${actual}`,
        '',
        'The file changed between `npm run browsers:require` and this launch, or the two are',
        'looking at different files. Re-run `npm run browsers:require` to re-validate and',
        'republish, and investigate why the executable changed if it was not expected.',
      ].join('\n'),
    );
  }

  return CHROMIUM_EXECUTABLE;
}

/* -------------------------------------------------------------------------- */
/* Environment                                                               */
/* -------------------------------------------------------------------------- */

/** Set by CI providers. Selects the CI branch of each setting keyed off it. */
const IS_CI = Boolean(process.env.CI);

/**
 * Hard ceiling on concurrent workers outside CI. Each worker is a whole browser process, so the
 * binding limit is memory and I/O.
 */
const MAX_LOCAL_WORKERS = 4;

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

  // One worker under CI. Locally, a quarter of the reported core count with
  // `MAX_LOCAL_WORKERS` as a hard ceiling and one worker as a floor, rather than
  // Playwright's default of half: every worker is a whole browser process, so the binding
  // limit is memory and I/O rather than cores. A small machine still parallelises and a
  // large one does not launch more browsers than its budget supports.
  //
  // @see docs/testing/DECISION-LOG.md - row D214.
  workers: IS_CI ? 1 : Math.max(1, Math.min(MAX_LOCAL_WORKERS, Math.floor(os.cpus().length / 4))),

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
    //
    // `sources: false` is the one reduction available here that costs no diagnosis.
    // A trace otherwise embeds a verbatim copy of every spec file it executed, and
    // `tests/configuration.spec.ts` declares four credential-shaped literals at
    // module scope - so the default packs those values into the artifact as source
    // text, in addition to the DOM and network records that are the point of it.
    // The source is in git at the same commit, so nothing a reader needs is lost.
    //
    // What still remains, stated rather than implied: the DOM snapshot, the trace
    // filmstrip, the failure screenshot and the video all show whatever the browser
    // showed, and `components/Configuration` renders `API Key` and `Access Token`
    // as `type="text"`. Playwright 1.44 offers no masking for automatic failure
    // evidence, and the AAP requires trace, screenshot and video on failure, so
    // that residue cannot be configured away. It is bounded at the source instead:
    // every value this suite types is asserted synthetic by the fixture-honesty
    // gate in `tests/configuration.spec.ts`, and CI retains these artifacts for
    // days rather than weeks.
    //
    // @see docs/testing/DECISION-LOG.md - row D318.
    trace: { mode: 'retain-on-failure', sources: false },
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
    // NO_EGRESS_BROWSER_ARGS. The `noEgress` fixture in `./tests/harness-fixtures.ts`
    // adds the mandatory context-wide rule on top, which is what attributes a
    // refusal to a test.
    launchOptions: {
      args: NO_EGRESS_BROWSER_ARGS,
      // `verifiedExecutable()`, not the raw variable: it re-hashes the file against the digest
      // `scripts/require-browser.js` published and throws on a mismatch, so the browser that
      // launches is the browser that was validated. See CHROMIUM_EXECUTABLE_DIGEST.
      ...(CHROMIUM_EXECUTABLE === undefined ? {} : { executablePath: verifiedExecutable() }),
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

    // Never reuse: every run starts its own harness, so the server under test is always
    // the one this configuration launched. With `strictPort: true` in the harness config
    // a held port fails the run.
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

/* -------------------------------------------------------------------------- */
/* Re-exports                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * The harness origin, and the only thing this file exports besides the configuration
 * itself. Re-exported so a spec can reach it without importing the Vite config directly.
 *
 * The `test` and `expect` every spec imports, and the two automatic fixtures that
 * complete them, live in `./tests/harness-fixtures.ts` - one module, so the contract
 * cannot drift between two definitions. That module imports `HARNESS_ORIGIN` from the
 * Vite config and re-exports it too, which is why a spec needs exactly one import.
 *
 * @see docs/testing/DECISION-LOG.md - rows D130, D131 and D286.
 */
export { HARNESS_ORIGIN };

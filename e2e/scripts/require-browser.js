#!/usr/bin/env node
/**
 * Resolves the Chromium-family browser this layer will run against, validates it, and
 * fails when there is none. Run by `npm run browsers:require` in `e2e/`.
 *
 * This script downloads nothing, ever. `@playwright/test` is pinned at 1.44.1, whose
 * browser downloader does not verify the TLS chain of the host it fetches from
 * (CVE-2025-59288), so every browser this layer uses is provisioned out of band from a
 * channel that signs its own artifacts. What this script adds is the missing half of
 * that arrangement: a check that the provisioning actually happened.
 *
 * It is the fail-closed companion to `browsers:verify`. That script runs
 * `playwright install --dry-run chromium`, which reports the build and cache directory
 * the runner expects and exits 0 whether or not the build is there - useful as a
 * report, useless as a gate. This one exits non-zero, and names the remedy.
 *
 * Resolution order, first hit wins:
 *
 *   1. `PLAYWRIGHT_CHROMIUM_EXECUTABLE`, which `e2e/playwright.config.ts` passes
 *      straight through as `launchOptions.executablePath`. An explicit value is never
 *      silently ignored: if it is set and unusable, this script fails on it rather
 *      than falling through to something else.
 *   2. A vendor-installed browser at one of the {@link VENDOR_CANDIDATES} paths for
 *      this platform - the location a signed `.deb`/`.rpm`, a macOS application
 *      bundle, or a Windows installer puts Chrome or Chromium.
 *   3. A Chromium build already in Playwright's own cache, which is what the runner
 *      uses when no executable path is supplied.
 *
 * On success it prints the route taken and the resolved path, and - for routes 1 and 2
 * - writes `PLAYWRIGHT_CHROMIUM_EXECUTABLE=<path>` to the file named by `GITHUB_ENV`
 * when that variable is set, so a CI job can resolve the browser in one step and have
 * every later step see it.
 *
 * Exit codes: 0 a usable browser was resolved; 1 none was, or an explicitly named one
 * is unusable.
 *
 * @see e2e/README.md - section 2, "The browser prerequisite", for the per-platform
 *   provisioning routes this script checks the result of.
 * @see docs/testing/DECISION-LOG.md - rows D111 and D129 (why nothing downloads a
 *   browser) and the row recording this gate.
 */

'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

/** Environment variable `playwright.config.ts` reads for an explicit executable. */
const EXECUTABLE_ENV = 'PLAYWRIGHT_CHROMIUM_EXECUTABLE';

/**
 * Vendor install locations checked on route 2, per `process.platform`.
 *
 * Every entry is a path an operating-system package manager or a vendor installer
 * writes - `google-chrome-stable`, `chromium` and `chromium-browser` from a distribution
 * or Google's own signed apt/yum repository, the macOS application bundles, and the
 * two Windows Program Files locations. None is a download target; each is only a place
 * to look.
 *
 * Ordered vendor-stable first, because a Chrome release is the build this layer has
 * been exercised against.
 */
const VENDOR_CANDIDATES = Object.freeze({
  linux: Object.freeze([
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/opt/google/chrome/chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/snap/bin/chromium',
  ]),
  darwin: Object.freeze([
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ]),
  win32: Object.freeze([
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Chromium\\Application\\chrome.exe',
  ]),
});

/**
 * Root of Playwright's own browser cache, per `process.platform`, matching what
 * `playwright-core` uses when `PLAYWRIGHT_BROWSERS_PATH` is unset.
 *
 * @returns Absolute cache directory.
 */
function playwrightCacheRoot() {
  const override = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (override !== undefined && override !== '' && override !== '0') {
    return override;
  }

  if (process.platform === 'win32') {
    return path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'ms-playwright');
  }
  if (process.platform === 'darwin') {
    return path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright');
  }
  return path.join(process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache'), 'ms-playwright');
}

/**
 * Executable names a cached Chromium build carries, per `process.platform`, relative to
 * that build's directory.
 *
 * @returns Relative paths to try inside a `chromium-*` cache directory.
 */
function cachedExecutableNames() {
  if (process.platform === 'win32') {
    return ['chrome-win\\chrome.exe'];
  }
  if (process.platform === 'darwin') {
    return [
      'chrome-mac/Chromium.app/Contents/MacOS/Chromium',
      'chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium',
    ];
  }
  return ['chrome-linux/chrome'];
}

/**
 * Reports whether `candidate` is a file this process could launch.
 *
 * Checks the type as well as the mode, because a directory of the same name would
 * otherwise pass an existence test and fail much later inside the runner. The execute
 * bit is not checked on Windows, where the filesystem does not carry one.
 *
 * @param candidate - Absolute path to test.
 * @returns `true` when it is a regular file and, off Windows, executable.
 */
function isLaunchable(candidate) {
  let stats;
  try {
    stats = fs.statSync(candidate);
  } catch {
    return false;
  }

  if (!stats.isFile()) {
    return false;
  }

  if (process.platform === 'win32') {
    return true;
  }

  try {
    fs.accessSync(candidate, fs.constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

/**
 * First launchable executable inside Playwright's cache, or `null`.
 *
 * Scans the cache root for `chromium-*` directories - the naming
 * `playwright install` uses, one directory per pinned build - and returns the first
 * whose executable is launchable.
 *
 * @returns Absolute path, or `null` when the cache holds no usable build.
 */
function findCachedChromium() {
  const root = playwrightCacheRoot();

  let entries;
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return null;
  }

  const builds = entries
    .filter((entry) => entry.isDirectory() && entry.name.startsWith('chromium'))
    .map((entry) => entry.name)
    .sort();

  for (const build of builds) {
    for (const relative of cachedExecutableNames()) {
      const candidate = path.join(root, build, relative);
      if (isLaunchable(candidate)) {
        return candidate;
      }
    }
  }

  return null;
}

/**
 * Per-platform provisioning instructions, printed when nothing resolved.
 *
 * Each names a channel that signs what it ships, which is the property CVE-2025-59288
 * costs the Playwright downloader.
 *
 * @returns Lines to print, without a trailing newline.
 */
function provisioningHelp() {
  const common = [
    `  - Set ${EXECUTABLE_ENV} to the full path of an existing Chrome or Chromium`,
    '    executable, and this check will accept it.',
  ];

  if (process.platform === 'win32') {
    return [
      '  - Install Google Chrome with the vendor installer, or `choco install googlechrome`,',
      `    which lands at ${VENDOR_CANDIDATES.win32[0]}.`,
      ...common,
    ];
  }
  if (process.platform === 'darwin') {
    return [
      '  - Install Google Chrome from google.com/chrome, or `brew install --cask google-chrome`,',
      `    which lands at ${VENDOR_CANDIDATES.darwin[0]}.`,
      ...common,
    ];
  }
  return [
    '  - Install from a signing repository, for example',
    '    `sudo apt-get install -y google-chrome-stable` with Google\'s apt key configured,',
    '    or `sudo apt-get install -y chromium`. A GitHub-hosted `ubuntu-latest` runner',
    `    already carries one at ${VENDOR_CANDIDATES.linux[0]}.`,
    ...common,
  ];
}

/**
 * Appends `PLAYWRIGHT_CHROMIUM_EXECUTABLE=<executable>` to the `GITHUB_ENV` file when
 * that variable names one, so later steps of the same job inherit the resolution.
 *
 * A failure to write is reported and does not fail the check: the browser was still
 * resolved, and the job can set the variable itself.
 *
 * @param executable - Path to publish.
 */
function publishToGithubEnv(executable) {
  const githubEnv = process.env.GITHUB_ENV;
  if (githubEnv === undefined || githubEnv === '') {
    return;
  }

  try {
    fs.appendFileSync(githubEnv, `${EXECUTABLE_ENV}=${executable}${os.EOL}`, 'utf8');
    process.stdout.write(`Published ${EXECUTABLE_ENV} to GITHUB_ENV for later steps.\n`);
  } catch (error) {
    process.stdout.write(`Could not write to GITHUB_ENV (${error.message}); set ${EXECUTABLE_ENV} in the job instead.\n`);
  }
}

/**
 * Resolves, validates and reports the browser, then exits.
 *
 * @returns Nothing; terminates the process.
 */
function main() {
  const explicit = process.env[EXECUTABLE_ENV];

  // Route 1. An explicit value is authoritative in both directions: it is used when it
  // works and it is an error when it does not, never silently replaced.
  if (explicit !== undefined && explicit !== '') {
    if (isLaunchable(explicit)) {
      process.stdout.write(`Browser resolved from ${EXECUTABLE_ENV}: ${explicit}\n`);
      process.exit(0);
    }

    process.stderr.write(
      [
        `${EXECUTABLE_ENV} is set to a path that is not a launchable executable:`,
        `  ${explicit}`,
        '',
        'Correct the value or unset it so the vendor and cache locations are searched.',
        '',
      ].join('\n'),
    );
    process.exit(1);
  }

  // Route 2. A browser the platform's own package manager or the vendor installed.
  for (const candidate of VENDOR_CANDIDATES[process.platform] || []) {
    if (isLaunchable(candidate)) {
      process.stdout.write(`Browser resolved from a vendor install: ${candidate}\n`);
      publishToGithubEnv(candidate);
      process.exit(0);
    }
  }

  // Route 3. A build already in Playwright's cache, used without an executable path.
  const cached = findCachedChromium();
  if (cached !== null) {
    process.stdout.write(`Browser resolved from the Playwright cache: ${cached}\n`);
    process.stdout.write(`Leaving ${EXECUTABLE_ENV} unset; the runner loads this build itself.\n`);
    process.exit(0);
  }

  process.stderr.write(
    [
      'No Chromium-family browser is available to the end-to-end suite.',
      '',
      `Searched, in order: ${EXECUTABLE_ENV} (unset), the vendor install locations for`,
      `${process.platform}, and the Playwright cache at ${playwrightCacheRoot()}.`,
      '',
      'Nothing here downloads one. @playwright/test is pinned at 1.44.1, whose downloader',
      'does not verify the TLS chain of the host it fetches from (CVE-2025-59288), so the',
      'browser is provisioned from a channel that signs its artifacts. Either:',
      '',
      ...provisioningHelp(),
      '',
      'See e2e/README.md section 2 and docs/testing/DECISION-LOG.md rows D111 and D129.',
      '',
    ].join('\n'),
  );
  process.exit(1);
}

main();

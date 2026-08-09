/**
 * The browser prerequisite gate for the end-to-end layer.
 *
 * `e2e/package.json` exposes this as `npm run browsers:verify`, and the `e2e` job of
 * `.github/workflows/ci.yml` runs it immediately before `npm test`. It answers one question and
 * answers it by looking at the filesystem: **is a Chromium executable this run can actually launch
 * already present?**
 *
 * It fetches nothing. `@playwright/test` is pinned at 1.44.1, whose browser downloader does not
 * verify the TLS chain of the host it fetches from, so no script in this package may invoke
 * `playwright install`. Browsers are provisioned out of band from a verified artifact and this file
 * confirms the result. See `docs/testing/DECISION-LOG.md` rows D111, D129 and D236.
 *
 * Two routes satisfy the prerequisite, checked in this order:
 *
 *   1. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` naming an existing, executable file. `e2e/playwright.config.ts`
 *      passes that value through as `launchOptions.executablePath`, so it is the exact file the run
 *      will launch.
 *   2. The Chromium build inside Playwright's own cache, at the exact path
 *      `chromium.executablePath()` reports for this pinned version.
 *
 * Exit status is the whole contract:
 *
 *   0  one route is satisfied; the resolved absolute path is printed.
 *   1  neither is; both routes are named, along with the exact path each was looked for at.
 *
 * The predecessor command, `playwright install --dry-run chromium`, could not do this: it prints the
 * install location it *would* use and exits 0 whether or not anything is there. Measured in this
 * container, it exited 0 while `fs.existsSync(chromium.executablePath())` was `false`.
 *
 * Run directly with `node scripts/verify-browser.js` from `e2e/`; it takes no arguments and reads no
 * configuration file.
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');

/** The environment variable `playwright.config.ts` reads for `launchOptions.executablePath`. */
const EXECUTABLE_ENV_VAR = 'PLAYWRIGHT_CHROMIUM_EXECUTABLE';

/**
 * Whether `candidate` is a file this process could launch.
 *
 * A directory, a dangling symlink and an unreadable entry all answer `false`. The executable bit is
 * checked with {@link fs.accessSync} rather than read off the mode, because Windows reports no
 * executable bit and `X_OK` degrades to an existence check there — which is the correct answer on a
 * platform where any readable `.exe` is launchable.
 *
 * @param {string} candidate Absolute or relative path to test.
 * @returns {boolean} `true` when the path resolves to a launchable file.
 */
function isLaunchableFile(candidate) {
  let stats;

  try {
    stats = fs.statSync(candidate);
  } catch (error) {
    return false;
  }

  if (!stats.isFile()) {
    return false;
  }

  try {
    fs.accessSync(candidate, fs.constants.X_OK);
  } catch (error) {
    return false;
  }

  return true;
}

/**
 * The path Playwright's cache would hold the pinned Chromium build at.
 *
 * `chromium.executablePath()` reports the expected location whether or not the build was ever
 * downloaded, which is exactly what this gate needs: the path to report in a failure message, and the
 * path to test for existence. Requiring `@playwright/test` performs no download and starts no browser.
 *
 * @returns {{path: string|null, error: string|null}} The absolute path, or the reason it is unknown.
 */
function cacheExecutablePath() {
  try {
    // eslint-disable-next-line global-require
    const { chromium } = require('@playwright/test');
    return { path: chromium.executablePath(), error: null };
  } catch (error) {
    return { path: null, error: error instanceof Error ? error.message : String(error) };
  }
}

/**
 * Resolves the prerequisite and reports it.
 *
 * @returns {number} The process exit code: `0` when a browser is present, `1` when none is.
 */
function main() {
  const configured = process.env[EXECUTABLE_ENV_VAR];
  const configuredPath = typeof configured === 'string' ? configured.trim() : '';

  if (configuredPath !== '') {
    const resolved = path.resolve(configuredPath);

    if (isLaunchableFile(resolved)) {
      process.stdout.write(
        `browser: ${EXECUTABLE_ENV_VAR} -> ${resolved}\n` +
          'The run will launch this executable through launchOptions.executablePath.\n',
      );
      return 0;
    }

    process.stderr.write(
      `${EXECUTABLE_ENV_VAR} is set to "${configuredPath}" but no launchable file exists there.\n` +
        `Looked at: ${resolved}\n` +
        'Point the variable at a Chromium or Chrome binary, or unset it to fall back to the ' +
        "Playwright cache. Nothing here downloads a browser.\n",
    );
    return 1;
  }

  const cache = cacheExecutablePath();

  if (cache.path === null) {
    process.stderr.write(
      `Could not resolve Playwright's expected Chromium path: ${cache.error}\n` +
        "Run `npm install` in e2e/ first, then set " +
        `${EXECUTABLE_ENV_VAR} to a browser provisioned from a verified artifact.\n`,
    );
    return 1;
  }

  if (isLaunchableFile(cache.path)) {
    process.stdout.write(
      `browser: Playwright cache -> ${cache.path}\n` +
        'The run will launch the cached build for the pinned @playwright/test version.\n',
    );
    return 0;
  }

  process.stderr.write(
    'No Chromium is available to this run, so every test would fail at launch.\n' +
      'Neither prerequisite route is satisfied:\n' +
      `  1. ${EXECUTABLE_ENV_VAR} is unset.\n` +
      `  2. Playwright's cache holds no build at ${cache.path}\n` +
      'Provision a browser out of band from a verified artifact, then either set ' +
      `${EXECUTABLE_ENV_VAR} to it or place the build at the path above. This command never ` +
      'downloads one: see docs/testing/DECISION-LOG.md rows D111, D129 and D236.\n',
  );
  return 1;
}

process.exitCode = main();

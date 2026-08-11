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
 *      will launch. When `PLAYWRIGHT_CHROMIUM_EXECUTABLE_SHA256` is also set - which
 *      `scripts/require-browser.js` does - the file is canonicalised and re-hashed against it, so
 *      this route answers *which* executable rather than merely whether one is there.
 *   2. The Chromium build inside Playwright's own cache, at the exact path
 *      `chromium.executablePath()` reports for this pinned version. No digest applies: no executable
 *      path is supplied to the runner on this route, so there is nothing a launch could re-check.
 *
 * Exit status is the whole contract:
 *
 *   0  one route is satisfied; the resolved absolute path is printed, with the confirmed digest
 *      when one was published.
 *   1  neither is - both routes are named, along with the exact path each was looked for at - or
 *      route 1's executable no longer matches its published digest.
 *
 * The predecessor command, `playwright install --dry-run chromium`, could not do this: it prints the
 * install location it *would* use and exits 0 whether or not anything is there. Measured in this
 * container, it exited 0 while `fs.existsSync(chromium.executablePath())` was `false`.
 *
 * Run directly with `node scripts/verify-browser.js` from `e2e/`; it takes no arguments and reads no
 * configuration file.
 */

'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

/** The environment variable `playwright.config.ts` reads for `launchOptions.executablePath`. */
const EXECUTABLE_ENV_VAR = 'PLAYWRIGHT_CHROMIUM_EXECUTABLE';

/**
 * The variable `scripts/require-browser.js` publishes the validated executable's SHA-256 in.
 *
 * Checked here as well as in `playwright.config.ts`, because this gate is what the `e2e` job runs
 * between the two: a swap that happened after resolution is caught by the step whose job is to
 * confirm, and named there, rather than surfacing later as a configuration-load error.
 *
 * @see docs/testing/DECISION-LOG.md - row D319.
 */
const DIGEST_ENV_VAR = 'PLAYWRIGHT_CHROMIUM_EXECUTABLE_SHA256';

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
 * Confirms `candidate` still hashes to the digest {@link DIGEST_ENV_VAR} names.
 *
 * Silent and successful when no digest was published, which is the normal local case: this reports
 * on a binding rather than requiring one. When a digest *is* published, a mismatch is fatal - the
 * point of publishing it was that the executable named here would be the executable that was
 * validated, and it is not.
 *
 * The path is canonicalised first, so a symlink repointed after resolution is measured at its new
 * target rather than at the name.
 *
 * @param {string} candidate Launchable path to confirm.
 * @returns {{ok: boolean, message: string}} Whether to proceed, and what to print.
 */
function confirmDigest(candidate) {
  const declared = process.env[DIGEST_ENV_VAR];
  const expected = typeof declared === 'string' ? declared.trim().toLowerCase() : '';

  if (expected === '') {
    return {
      ok: true,
      message:
        `Not digest-bound: ${DIGEST_ENV_VAR} is unset, so this check confirms the path only. Run ` +
        '`npm run browsers:require` to publish a digest and bind the launch to this exact file.\n',
    };
  }

  let real = candidate;
  try {
    real = fs.realpathSync(candidate);
  } catch (error) {
    // Left as the given path: it was already proven launchable, and reporting the digest of what
    // is actually there is still the useful answer.
  }

  let actual;
  try {
    actual = crypto.createHash('sha256').update(fs.readFileSync(real)).digest('hex');
  } catch (error) {
    return {
      ok: false,
      message:
        `${DIGEST_ENV_VAR} is set but ${real} could not be read to confirm it: ` +
        `${error instanceof Error ? error.message : String(error)}\n`,
    };
  }

  if (actual !== expected) {
    return {
      ok: false,
      message:
        'The executable does not match the digest that was published for it, so it is not the ' +
        'browser that was validated.\n' +
        `  path:     ${real}\n` +
        `  expected: ${expected}\n` +
        `  actual:   ${actual}\n` +
        'Re-run `npm run browsers:require` to re-validate and republish, and investigate why the ' +
        'file changed if that was not expected.\n',
    };
  }

  return { ok: true, message: `SHA-256 confirmed against ${DIGEST_ENV_VAR}: ${actual}\n` };
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
      const confirmed = confirmDigest(resolved);

      if (!confirmed.ok) {
        process.stderr.write(confirmed.message);
        return 1;
      }

      process.stdout.write(
        `browser: ${EXECUTABLE_ENV_VAR} -> ${resolved}\n` +
          'The run will launch this executable through launchOptions.executablePath.\n' +
          confirmed.message,
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

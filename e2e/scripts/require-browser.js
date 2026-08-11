#!/usr/bin/env node
/**
 * Resolves the Chromium-family browser this layer will run against, validates it,
 * publishes it, and fails when there is none. Run by `npm run browsers:require` in
 * `e2e/`.
 *
 * This script downloads nothing, ever. `@playwright/test` is pinned at 1.44.1, whose
 * browser downloader does not verify the TLS chain of the host it fetches from
 * (CVE-2025-59288), so every browser this layer uses is provisioned out of band from a
 * channel that signs its own artifacts. What this script adds is the missing half of
 * that arrangement: a check that the provisioning actually happened, and a single
 * recorded answer to which executable the run will launch.
 *
 * It is the resolving, fail-closed **gate**, and `browsers:verify` is the narrower
 * **reporter** over the same provision - an explicit executable and Playwright's own
 * cache - which also exits non-zero when neither is launchable; it simply does not
 * search the platform's vendor install locations and publishes nothing. The `e2e` job
 * runs this one first for that reason. Use `browsers:require` to decide whether a run
 * can proceed; use `browsers:verify` to see what a run without an explicit executable
 * would load. Neither fetches anything. (An earlier arrangement used `playwright install
 * --dry-run chromium` for the confirming half, which was useless as a gate - it exits 0
 * whether or not the build is present - and no script in this package invokes the
 * downloader now.)
 *
 * Resolution order, first hit wins:
 *
 *   1. `PLAYWRIGHT_CHROMIUM_EXECUTABLE`, which `e2e/playwright.config.ts` passes
 *      straight through as `launchOptions.executablePath`. An explicit value is never
 *      silently ignored: if it is set and unusable, this script fails on it rather
 *      than falling through to something else.
 *   2. `CHROME_BIN`, the conventional variable a CI image or a developer sets to name a
 *      browser. Treated exactly like route 1 - authoritative in both directions.
 *   3. A vendor-installed browser at one of the {@link VENDOR_CANDIDATES} paths for
 *      this platform - the location a signed `.deb`/`.rpm`, a macOS application
 *      bundle, or a Windows installer puts Chrome or Chromium.
 *   4. The Chromium build in Playwright's own cache, at the exact path
 *      `chromium.executablePath()` reports for this pinned version. That call is the
 *      only correct source for this route: Playwright loads the build matching its own
 *      pinned revision and nothing else, it is the only thing that knows where
 *      `PLAYWRIGHT_BROWSERS_PATH` - including the value `0`, which relocates the cache
 *      inside the `playwright-core` package - actually points, and it reports the path
 *      whether or not the build was ever downloaded. Requiring `@playwright/test`
 *      performs no download and starts no browser.
 *
 * On every route it prints the route taken, the resolved path, the **canonical** path with
 * symlinks resolved, the executable's SHA-256, and a note for anything about it this user
 * could overwrite; it reads the resolved build's `--version` so the run records which
 * browser it got rather than only where it came from; and it writes both
 * `PLAYWRIGHT_CHROMIUM_EXECUTABLE=<canonical path>` and
 * `PLAYWRIGHT_CHROMIUM_EXECUTABLE_SHA256=<digest>` to the file named by `GITHUB_ENV` when
 * that variable is set. Publishing on the cache route as well as on the others is
 * deliberate: the runner would otherwise resolve the cache a second time, independently,
 * and the path recorded in the log would not be provably the path launched.
 * Both are published in GitHub's delimited multi-line form with a random delimiter, so a
 * value is bounded by a token no path can contain, and a path carrying CR or LF is not
 * published at all.
 *
 * The digest is the point of the canonicalisation, and it is what turns this from a check
 * into a binding. Validating a *path* and then launching that path later establishes
 * nothing: a symlink can be repointed and a user-writable file can be replaced in
 * between, and the run would launch something this script never saw.
 * `playwright.config.ts` recomputes the digest before the launch and refuses a mismatch,
 * so the two ends of that window are tied together.
 *
 * `--min-major <n>` additionally refuses a resolved build whose major version is below
 * `n`, so an image carrying an ancient browser fails at this gate with a version in the
 * message instead of somewhere inside a spec.
 *
 * Exit codes: 0 a usable browser was resolved; 1 none was, an explicitly named one is
 * unusable, or the resolved build is below the required major version.
 *
 * @see e2e/README.md - section 2, "The browser prerequisite", for the per-platform
 *   provisioning routes this script checks the result of.
 * @see docs/testing/DECISION-LOG.md - rows D111 and D129 (why nothing downloads a
 *   browser), the rows recording this gate, and row D319 (the digest binding).
 */

'use strict';

const { execFileSync } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

/** Environment variable `playwright.config.ts` reads for an explicit executable. */
const EXECUTABLE_ENV = 'PLAYWRIGHT_CHROMIUM_EXECUTABLE';

/** Conventional variable a CI image or a developer sets to name a browser. */
const CHROME_BIN_ENV = 'CHROME_BIN';

/**
 * Environment variable carrying the SHA-256 of the executable this script validated.
 *
 * The reason it exists: without it, this script and the process that actually launches the
 * browser share only a *path*. This one validates a file, prints a reassuring line and exits;
 * `playwright.config.ts` then hands the same path to `launchOptions.executablePath` at some later
 * moment, and nothing connects the two - so whatever was checked here is not necessarily what
 * runs. Publishing the digest closes that by making the claim checkable: `playwright.config.ts`
 * recomputes it before the launch and refuses a mismatch.
 *
 * @see docs/testing/DECISION-LOG.md - row D319.
 */
const DIGEST_ENV = 'PLAYWRIGHT_CHROMIUM_EXECUTABLE_SHA256';

/**
 * Vendor install locations checked on route 3, per `process.platform`.
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
 * Reports whether `candidate` is a file this process could launch.
 *
 * Checks the type as well as the mode: a directory of the same name passes an
 * existence test and is not launchable. The execute bit is not checked on Windows,
 * where the filesystem does not carry one. A path carrying CR or LF is rejected
 * before the filesystem is consulted, so no such path can be resolved, printed or
 * published.
 *
 * @param candidate - Absolute path to test.
 * @returns `true` when it is a regular file and, off Windows, executable.
 */
function isLaunchable(candidate) {
  if (typeof candidate !== 'string' || carriesLineBreak(candidate)) {
    return false;
  }

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
 * The exact path Playwright's own cache holds the pinned Chromium build at.
 *
 * Delegated to `playwright-core`'s registry through `chromium.executablePath()` rather
 * than reconstructed here. That call resolves the revision this pin loads, honours
 * `PLAYWRIGHT_BROWSERS_PATH` in all of its forms, and reports the expected location
 * whether or not anything is there - so the same value serves as the path to test and
 * as the path to name in a failure message.
 *
 * @returns `{ path, error }` - the absolute path, or the reason it is unknown.
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

/** A four-part Chromium version, as its install layout spells one. */
const VERSION_DIRECTORY = /^\d+\.\d+\.\d+\.\d+$/;

/**
 * The version recorded in the install layout beside `executable`, or `null`.
 *
 * A Windows Chrome or Chromium install puts a version-named directory next to
 * `chrome.exe`, which is the only version string available there: `chrome.exe
 * --version` writes nothing to a redirected stdout on that platform, so the
 * subprocess reading below legitimately comes back empty and this is the fallback
 * that keeps the recorded identity real rather than absent.
 *
 * @param executable - Path whose sibling directories to inspect.
 * @returns The version string, or `null` when the layout carries none.
 */
function versionFromInstallLayout(executable) {
  try {
    const siblings = fs
      .readdirSync(path.dirname(executable), { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && VERSION_DIRECTORY.test(entry.name))
      .map((entry) => entry.name)
      .sort();
    return siblings.length === 0 ? null : siblings[siblings.length - 1];
  } catch {
    return null;
  }
}

/**
 * Reads the version of a resolved browser.
 *
 * Tries `--version` first and the install layout second. A build that reports neither
 * is still accepted: the launchability check above is the gate, and a headless-only or
 * sandboxed build can legitimately refuse to print a version while launching correctly
 * under Playwright. What this adds is the recorded identity of the build a run used,
 * so a report says which browser produced it and not only where it came from.
 *
 * @param executable - Path to interrogate.
 * @returns `{ raw, major }` - the version reading and its leading major number, either
 *   of which may be `null`.
 */
function readVersion(executable) {
  let raw = null;
  try {
    raw = execFileSync(executable, ['--version'], {
      encoding: 'utf8',
      timeout: 30_000,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    raw = null;
  }

  if (raw === null || raw === '') {
    const layout = versionFromInstallLayout(executable);
    raw = layout === null ? null : `${layout} (from the install layout)`;
  }

  if (raw === null) {
    return { raw: null, major: null };
  }

  const match = /(\d+)\.\d+/.exec(raw);
  return { raw, major: match === null ? null : Number(match[1]) };
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
    `  - Set ${EXECUTABLE_ENV} (or ${CHROME_BIN_ENV}) to the full path of an existing`,
    '    Chrome or Chromium executable, and this check will accept it.',
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
/**
 * Whether `candidate` contains a character that would end a line in an environment
 * file.
 *
 * @param candidate - Path to test.
 * @returns `true` when the path carries CR or LF.
 */
function carriesLineBreak(candidate) {
  return /[\r\n]/.test(candidate);
}

/**
 * Canonical on-disk path of `candidate`, with every symlink and junction resolved.
 *
 * Everything downstream is keyed to this rather than to the name that was typed. A name is a
 * mutable pointer: `/usr/bin/google-chrome` is a symlink on most distributions, and a link that
 * validated a moment ago can be repointed at an arbitrary file without touching the name at all.
 * The canonical path is the thing whose contents were read, so it is the thing worth publishing.
 *
 * @param candidate - Path to canonicalise.
 * @returns Absolute real path, or `null` when it cannot be resolved.
 */
function realPathOf(candidate) {
  try {
    return fs.realpathSync(candidate);
  } catch {
    return null;
  }
}
/**
 * SHA-256, hex, of the file at `candidate`.
 *
 * Read in chunks rather than whole: a Chrome binary is tens of megabytes on some platforms, and
 * there is no reason to hold one in memory to hash it. Measured cost on the browser this suite
 * runs against is well under a second.
 *
 * @param candidate - File to hash.
 * @returns Lower-case hex digest, or `null` when the file cannot be read.
 */
function sha256Of(candidate) {
  try {
    const hash = crypto.createHash('sha256');
    const CHUNK_BYTES = 1 << 20;
    const buffer = Buffer.allocUnsafe(CHUNK_BYTES);
    const handle = fs.openSync(candidate, 'r');
    try {
      for (;;) {
        const read = fs.readSync(handle, buffer, 0, CHUNK_BYTES, null);
        if (read === 0) {
          break;
        }
        hash.update(buffer.subarray(0, read));
      }
    } finally {
      fs.closeSync(handle);
    }
    return hash.digest('hex');
  } catch {
    return null;
  }
}
/**
 * Whether this process could overwrite `candidate` or the directory holding it.
 *
 * Reported, never fatal. A browser the current user can replace is a browser whose validation
 * means less than it appears to - anything running as this user can swap it between the check and
 * the launch, and the digest below is what makes that swap visible rather than silent. Vendor
 * installs under `/opt`, `/usr/bin` or `Program Files` are normally not user-writable, so this is
 * usually quiet; it speaks up for a browser unpacked into a home directory or a shared temp path.
 *
 * @param candidate - Canonical path to the executable.
 * @returns Array of human-readable findings, empty when neither is writable.
 */
function writabilityFindings(candidate) {
  const findings = [];
  const targets = [
    [candidate, 'the executable itself'],
    [path.dirname(candidate), 'the directory holding it'],
  ];

  for (const [target, description] of targets) {
    try {
      fs.accessSync(target, fs.constants.W_OK);
      findings.push(`${description} (${target}) is writable by this user`);
    } catch {
      // Not writable, which is the expected case for a vendor install.
    }
  }

  return findings;
}
/**
 * Canonicalises `candidate`, hashes it, and reports what it found.
 *
 * @param candidate - Launchable path, already checked by {@link isLaunchable}.
 * @returns `{ realPath, digest, writable }`, or `null` when it could not be read after all.
 */
function describeExecutable(candidate) {
  const realPath = realPathOf(candidate);
  if (realPath === null) {
    return null;
  }

  const digest = sha256Of(realPath);
  if (digest === null) {
    return null;
  }

  return { realPath, digest, writable: writabilityFindings(realPath) };
}
/**
 * Prints the canonical path, the digest, and any writability finding.
 *
 * The digest is printed whether or not it can be published, because a local run has no
 * `GITHUB_ENV`: printing it is what lets someone set {@link DIGEST_ENV} by hand and get the same
 * launch-time check CI gets.
 *
 * @param described - Result of {@link describeExecutable}.
 * @param original - The path as it was resolved, before canonicalisation.
 */
function reportExecutable(described, original) {
  if (described.realPath !== original) {
    process.stdout.write(`Canonical path (symlinks resolved): ${described.realPath}\n`);
  }
  process.stdout.write(`SHA-256: ${described.digest}\n`);

  for (const finding of described.writable) {
    process.stdout.write(`Note: ${finding}.\n`);
  }
  if (described.writable.length > 0) {
    process.stdout.write(
      `Anything running as this user could replace it before the launch. ${DIGEST_ENV} is what makes that visible.\n`,
    );
  }
}
/**
 * Reports a path that resolved and is a file, but whose contents could not be read.
 *
 * Fails rather than proceeding: an executable that cannot be read cannot be launched either, and
 * accepting it here would defer a certain failure into the middle of the run.
 *
 * @param candidate - Path that could not be described.
 * @returns Nothing; terminates the process.
 */
function exitUnreadable(candidate) {
  process.stderr.write(
    [
      'A Chromium-family browser was found but could not be read:',
      `  ${candidate}`,
      '',
      'It resolved to a regular file, so this is a permission or I/O problem rather than a',
      'missing browser. The launch would fail the same way. Correct the permissions, or name a',
      `different executable with ${EXECUTABLE_ENV}.`,
      '',
    ].join('\n'),
  );
  process.exit(1);
}
/**
 * Appends the canonical path and its digest to the `GITHUB_ENV` file when that variable names
 * one, so later steps of the same job launch exactly the file this step validated.
 *
 * Both variables are published together, always. The path alone is what the previous version
 * wrote, and a path is only a name: publishing the digest beside it is what lets
 * `playwright.config.ts` establish that the name still refers to the same bytes.
 *
 * A failure to write is reported and does not fail the check: the browser was still resolved, and
 * the job can set the variables itself.
 *
 * @param described - Result of {@link describeExecutable}.
 */
function publishToGithubEnv(described) {
  const githubEnv = process.env.GITHUB_ENV;
  if (githubEnv === undefined || githubEnv === '') {
    return;
  }

  if (carriesLineBreak(described.realPath)) {
    process.stdout.write(
      `Refusing to publish ${EXECUTABLE_ENV}: the resolved path contains a line break. ` +
        `Set ${EXECUTABLE_ENV} and ${DIGEST_ENV} in the job instead.\n`,
    );
    return;
  }

  let delimiter = `ghenv_${crypto.randomBytes(16).toString('hex')}`;
  while (described.realPath.includes(delimiter) || described.digest.includes(delimiter)) {
    delimiter = `ghenv_${crypto.randomBytes(16).toString('hex')}`;
  }

  const lines =
    `${EXECUTABLE_ENV}<<${delimiter}${os.EOL}${described.realPath}${os.EOL}${delimiter}${os.EOL}` +
    `${DIGEST_ENV}<<${delimiter}${os.EOL}${described.digest}${os.EOL}${delimiter}${os.EOL}`;

  try {
    fs.appendFileSync(githubEnv, lines, 'utf8');
    process.stdout.write(`Published ${EXECUTABLE_ENV} and ${DIGEST_ENV} to GITHUB_ENV for later steps.\n`);
  } catch (error) {
    process.stdout.write(
      `Could not write to GITHUB_ENV (${error.message}); set ${EXECUTABLE_ENV} and ${DIGEST_ENV} in the job instead.\n`,
    );
  }
}

/**
 * Reads an optional filesystem path from the environment.
 *
 * An unset variable and one holding only whitespace are the same answer: no path was
 * supplied. Both matter, because a GitHub Actions expression whose variable is not
 * defined expands to the empty string rather than removing the variable from the
 * environment, so a blank value must fall through rather than fail.
 *
 * @param name - Variable to read.
 * @returns The trimmed value, or `null` when unset or blank.
 */
function readOptionalPath(name) {
  const raw = process.env[name];
  if (typeof raw !== 'string') {
    return null;
  }
  const trimmed = raw.trim();
  return trimmed === '' ? null : trimmed;
}

/**
 * Parses `--min-major <n>` out of the argument vector.
 *
 * @param argv - Arguments after the script name.
 * @returns The required major version, or `null` when none was requested.
 */
function parseMinMajor(argv) {
  const index = argv.indexOf('--min-major');
  if (index === -1) {
    return null;
  }
  const value = Number(argv[index + 1]);
  if (!Number.isInteger(value) || value <= 0) {
    process.stderr.write('--min-major requires a positive integer.\n');
    process.exit(1);
  }
  return value;
}

function accept(route, executable, minMajor) {
  const resolved = path.resolve(executable);
  process.stdout.write(`Browser resolved from ${route}: ${resolved}\n`);

  const described = describeExecutable(resolved);
  if (described === null) {
    exitUnreadable(resolved);
  }

  reportExecutable(described, resolved);

  const version = readVersion(described.realPath);
  process.stdout.write(`Browser version: ${version.raw === null ? 'not reported' : version.raw}\n`);

  if (minMajor !== null && version.major !== null && version.major < minMajor) {
    process.stderr.write(
      [
        `The resolved browser reports major version ${version.major}, below the required ${minMajor}:`,
        `  ${described.realPath}`,
        '',
        `Provision a newer build and name it with ${EXECUTABLE_ENV}. Nothing here downloads one.`,
        '',
      ].join('\n'),
    );
    process.exit(1);
  }

  publishToGithubEnv(described);
  process.exit(0);
}

/**
 * Fails on an explicitly named executable that cannot be launched.
 *
 * @param variable - Which variable named it.
 * @param value - The value it held.
 * @returns Nothing; terminates the process.
 */
function refuseExplicit(variable, value) {
  process.stderr.write(
    [
      `${variable} is set to a path that is not a launchable executable:`,
      `  ${value}`,
      '',
      'Correct the value or unset it so the vendor and cache locations are searched.',
      '',
    ].join('\n'),
  );
  process.exit(1);
}

/**
 * Resolves, validates, records and publishes the browser, then exits.
 *
 * @returns Nothing; terminates the process.
 */
function main() {
  const minMajor = parseMinMajor(process.argv.slice(2));

  // Routes 1 and 2. An explicit value is authoritative in both directions: it is used
  // when it works and it is an error when it does not, never silently replaced.
  for (const variable of [EXECUTABLE_ENV, CHROME_BIN_ENV]) {
    const explicit = readOptionalPath(variable);
    if (explicit === null) {
      continue;
    }
    if (isLaunchable(explicit)) {
      accept(variable, explicit, minMajor);
    }
    refuseExplicit(variable, explicit);
  }

  // Route 3. A browser the platform's own package manager or the vendor installed.
  for (const candidate of VENDOR_CANDIDATES[process.platform] || []) {
    if (isLaunchable(candidate)) {
      accept('a vendor install', candidate, minMajor);
    }
  }

  // Route 4. The build in Playwright's cache, at the exact path the runner loads.
  const cached = cacheExecutablePath();
  if (cached.path !== null && isLaunchable(cached.path)) {
    accept('the Playwright cache', cached.path, minMajor);
  }

  process.stderr.write(
    [
      'No Chromium-family browser is available to the end-to-end suite.',
      '',
      `Searched, in order: ${EXECUTABLE_ENV} (unset or blank), ${CHROME_BIN_ENV} (unset or`,
      `blank), the vendor install locations for ${process.platform}, and Playwright's own`,
      cached.path === null
        ? `cache, whose path could not be resolved: ${cached.error}`
        : `cache at ${cached.path}`,
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

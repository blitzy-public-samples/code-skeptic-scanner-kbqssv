/**
 * Dependency-closure gate for the frontend and e2e npm packages.
 *
 * ## Subject
 *
 * `frontend/package.json` and `e2e/package.json` are the repository's only npm manifests, and neither
 * package commits a lockfile. A range specifier therefore means a clean `npm install` may resolve a package
 * the suite has never been run against - which is how a compromised patch release enters a project that
 * looked pinned.
 *
 * The two manifests are not equally open to this suite, and that is what shapes the assertions below.
 * `e2e/package.json` is a file this testing work created in full, so every one of its declarations is ours to
 * pin. `frontend/package.json` existed before it, and the frozen plan authorises changes to its **test
 * devDependencies and test scripts only** - explicitly, nothing else in that file changes. Its seven runtime
 * dependencies and ten pre-existing development declarations are therefore outside what this suite may
 * require anything of, beyond that they are still exactly what the repository declared.
 *
 * So `frontend/package.json` is asserted as a partition of two sets:
 *
 * | Set                       | Members                                              | Asserted                                                        |
 * |---------------------------|------------------------------------------------------|-----------------------------------------------------------------|
 * | {@link SUITE_OWNED_PINS}  | the 11 test devDependencies this work introduced      | exact pin, the exact version the plan names, and installed at it |
 * | {@link BASELINE_DECLARATIONS} | the 17 declarations the repository already carried | byte-identical to the baseline specifier, and installed at a version that specifier admits |
 *
 * A declaration in neither set fails the partition case, so a future addition cannot enter unasserted.
 *
 * It is the Jest counterpart of `backend/tests/test_dependency_closure.py`, which does the same for
 * `backend/requirements-dev.txt` - a file this work created in full, and therefore pins throughout.
 *
 * ## What it deliberately does not assert
 *
 * The **transitive** graph, for either manifest. Without a lockfile there is no integrity-hashed reference to
 * compare a transitive tree against, and this module invents none: it would be asserting one uncontrolled tree
 * against another.
 *
 * And, for the baseline set only, an *exact* installed version. Those declarations are ranges, so a clean
 * install may legitimately resolve a newer release than the one this suite last ran against; what is asserted
 * is that the resolved release is one the declared range admits. Both residuals are real and recorded rather
 * than papered over - see the decision log.
 *
 * `e2e/node_modules` is not read at all: that tree belongs to the Playwright runner rather than to Jest, so
 * only the manifest's *shape* is checked, because it is committed configuration governed by the same finding.
 *
 * ## Scope
 *
 * Reads files off disk and nothing else. It imports no application module, renders nothing and opens no
 * socket, so the msw interception the shared setup installs is never engaged.
 *
 * @see backend/tests/test_dependency_closure.py - the backend gate this mirrors.
 * @see docs/testing/DECISION-LOG.md - why exact pins plus a gate rather than a committed lockfile, why the
 *   pre-existing declarations are asserted unchanged rather than pinned, and the residuals both choices carry.
 */

import { readFileSync } from 'fs';
import { join, resolve } from 'path';

/** Repository root, resolved from this file: `src/test-utils` -> `frontend` -> repository root. */
const REPOSITORY_ROOT = resolve(__dirname, '..', '..', '..');

/** `frontend/`, the package Jest runs in and the only one whose installed tree is read here. */
const FRONTEND_ROOT = join(REPOSITORY_ROOT, 'frontend');

/** `e2e/`, whose manifest is checked for shape only. */
const E2E_ROOT = join(REPOSITORY_ROOT, 'e2e');

/**
 * An exact version: three numeric components, with an optional prerelease and build suffix. Anything a
 * consumer could read as a range - `^`, `~`, `>`, `<`, `=`, `*`, `x`, ` || `, ` - `, a `git`/`file:`/
 * `npm:` specifier, or the empty string - fails to match, which is the whole point of the pattern.
 */
const EXACT_VERSION = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z-.]+)?(?:\+[0-9A-Za-z-.]+)?$/;

/** The two dependency blocks a direct dependency can be declared in. */
const DEPENDENCY_BLOCKS = ['dependencies', 'devDependencies'] as const;

/**
 * The test dependencies this work added to `frontend/package.json`, each at the exact version the frozen plan
 * names. `jest` and `ts-jest` are here rather than in {@link BASELINE_DECLARATIONS} because the plan pins
 * those two by name, replacing the ranges the repository declared.
 */
const SUITE_OWNED_PINS: Readonly<Record<string, string>> = Object.freeze({
  jest: '29.7.0',
  'ts-jest': '29.4.12',
  'jest-environment-jsdom': '29.5.0',
  '@types/jest': '29.5.12',
  'jest-junit': '16.0.0',
  msw: '1.3.5',
  '@reduxjs/toolkit': '1.9.7',
  'react-redux': '8.1.3',
  'react-router-dom': '6.22.3',
  zod: '3.22.4',
  dayjs: '1.11.10',
});

/**
 * Every other declaration in `frontend/package.json`, with the specifier the repository carried before this
 * testing work began. These are outside the authorised change surface, so the assertion is that they are
 * untouched - a value here differing from the manifest means something changed a declaration it may not.
 */
const BASELINE_DECLARATIONS: Readonly<Record<string, string>> = Object.freeze({
  react: '^18.2.0',
  'react-dom': '^18.2.0',
  'react-query': '^3.39.3',
  'chart.js': '^4.3.0',
  'react-chartjs-2': '^5.2.0',
  tailwindcss: '^3.3.2',
  axios: '^1.4.0',
  '@types/react': '^18.2.7',
  '@types/react-dom': '^18.2.4',
  '@testing-library/react': '^14.0.0',
  '@testing-library/jest-dom': '^5.16.5',
  '@testing-library/user-event': '^14.4.3',
  typescript: '^5.0.4',
  vite: '^4.3.9',
  '@vitejs/plugin-react': '^4.0.0',
  autoprefixer: '^10.4.14',
  postcss: '^8.4.23',
});

interface Manifest {
  readonly dependencies?: Record<string, string>;
  readonly devDependencies?: Record<string, string>;
  readonly version?: string;
}

/** One declared dependency, flattened out of whichever block declared it. */
interface DeclaredDependency {
  /** `dependencies` or `devDependencies`. */
  readonly block: string;
  readonly name: string;
  /** The specifier exactly as the manifest carries it. */
  readonly specifier: string;
}

/**
 * Parses a manifest off disk.
 *
 * @param manifestPath - Absolute path to a `package.json`.
 * @returns The parsed object.
 */
function readManifest(manifestPath: string): Manifest {
  return JSON.parse(readFileSync(manifestPath, 'utf8')) as Manifest;
}

/**
 * Flattens both dependency blocks of a manifest into one list, in declaration order.
 *
 * @param manifest - A parsed `package.json`.
 * @returns Every direct dependency it declares.
 */
function declaredDependencies(manifest: Manifest): DeclaredDependency[] {
  return DEPENDENCY_BLOCKS.flatMap((block) =>
    Object.entries(manifest[block] ?? {}).map(([name, specifier]) => ({
      block,
      name,
      specifier,
    })),
  );
}

/** The three numeric components of a version, ignoring any prerelease or build suffix. */
function versionParts(version: string): [number, number, number] {
  const [major, minor, patch] = version
    .replace(/^[^\d]*/, '')
    .split(/[-+]/)[0]
    .split('.')
    .map((part) => Number.parseInt(part, 10));
  return [major, minor, patch];
}

/**
 * Whether `installed` is a release the specifier admits, for the two specifier forms these manifests use: an
 * exact version, which admits only itself, and a caret range, which admits any release at or above it that
 * keeps the same major.
 *
 * Hand-written rather than delegated to `semver`, which is present only as a transitive dependency of Jest and
 * so is not a package either manifest declares. The two forms above are the only ones reachable, because the
 * partition cases below assert every specifier is one of them.
 *
 * @param specifier - The declared specifier, `1.2.3` or `^1.2.3`.
 * @param installed - The `version` field of the installed package.
 */
function admitsInstalledVersion(specifier: string, installed: string): boolean {
  const [declaredMajor, declaredMinor, declaredPatch] = versionParts(specifier);
  const [installedMajor, installedMinor, installedPatch] = versionParts(installed);

  if (!specifier.startsWith('^')) {
    return specifier === installed;
  }

  if (installedMajor !== declaredMajor) {
    return false;
  }
  if (installedMinor !== declaredMinor) {
    return installedMinor > declaredMinor;
  }
  return installedPatch >= declaredPatch;
}

/**
 * The `version` the installed copy of `name` reports.
 *
 * Read from the package's own `package.json` inside `node_modules` rather than through `require.resolve`,
 * which would follow the `main` field and fail on a package that exposes no entry point, and rather than
 * through `npm ls`, which would mean spawning a process from a test.
 *
 * @param name - Package name as declared.
 * @param specifier - Included in the failure message so an uninstalled package names what was expected.
 * @throws Error naming the unreadable path and the install command that fixes it.
 */
function installedVersion(name: string, specifier: string): string | undefined {
  const installedPath = join(FRONTEND_ROOT, 'node_modules', name, 'package.json');

  try {
    return readManifest(installedPath).version;
  } catch (error) {
    throw new Error(
      `${name} is declared as ${specifier} in frontend/package.json and is not installed ` +
        `(${installedPath} is unreadable). Run: npm install --prefix frontend. ` +
        `Underlying error: ${String(error)}`,
    );
  }
}

const frontendManifest = readManifest(join(FRONTEND_ROOT, 'package.json'));
const e2eManifest = readManifest(join(E2E_ROOT, 'package.json'));

const frontendDependencies = declaredDependencies(frontendManifest);
const e2eDependencies = declaredDependencies(e2eManifest);

const frontendSpecifiers = new Map(
  frontendDependencies.map((entry) => [entry.name, entry.specifier] as const),
);

/**
 * A guard, not a formality: every parametrised block below iterates a list read off disk or a table compared
 * against one, so an emptied, renamed or restructured manifest would otherwise degenerate to zero cases and
 * report green.
 */
describe('manifest parsing', () => {
  it('finds direct dependencies declared in frontend/package.json', () => {
    expect(frontendDependencies.length).toBeGreaterThan(0);
  });

  it('finds direct dependencies declared in e2e/package.json', () => {
    expect(e2eDependencies.length).toBeGreaterThan(0);
  });
});

describe('frontend/package.json declarations are partitioned into the two governed sets', () => {
  it('declares every suite-owned pin and every baseline declaration, and nothing else', () => {
    const governed = [...Object.keys(SUITE_OWNED_PINS), ...Object.keys(BASELINE_DECLARATIONS)].sort();

    expect([...frontendSpecifiers.keys()].sort()).toEqual(governed);
  });

  it('keeps the two sets disjoint', () => {
    const overlap = Object.keys(SUITE_OWNED_PINS).filter((name) => name in BASELINE_DECLARATIONS);

    expect(overlap).toEqual([]);
  });

  it('declares every specifier in one of the two forms the version comparison handles', () => {
    const unsupported = frontendDependencies.filter(
      (entry) => !EXACT_VERSION.test(entry.specifier) && !EXACT_VERSION.test(entry.specifier.slice(1)),
    );

    expect(unsupported).toEqual([]);
  });
});

describe('the test dependencies this suite owns are pinned exactly', () => {
  it.each(Object.entries(SUITE_OWNED_PINS))('%s is declared as exactly %s', (name, expected) => {
    const specifier = frontendSpecifiers.get(name);

    expect(specifier).toMatch(EXACT_VERSION);
    expect(specifier).toBe(expected);
  });

  it.each(Object.entries(SUITE_OWNED_PINS))('%s is installed at exactly %s', (name, expected) => {
    expect(installedVersion(name, expected)).toBe(expected);
  });
});

describe('the declarations this suite may not change are unchanged', () => {
  it.each(Object.entries(BASELINE_DECLARATIONS))('%s still declares %s', (name, expected) => {
    expect(frontendSpecifiers.get(name)).toBe(expected);
  });

  it.each(Object.entries(BASELINE_DECLARATIONS))(
    '%s is installed at a version %s admits',
    (name, specifier) => {
      const installed = installedVersion(name, specifier);

      expect(installed).toBeDefined();
      expect(admitsInstalledVersion(specifier, String(installed))).toBe(true);
    },
  );
});

describe('e2e/package.json declares exact versions only', () => {
  it.each(e2eDependencies.map((entry) => [`${entry.block}/${entry.name}`, entry] as const))(
    '%s is pinned exactly',
    (_label, entry) => {
      expect(entry.specifier).toMatch(EXACT_VERSION);
    },
  );
});

/**
 * The rule whose absence lets the properties above be enforced at all: with `package-lock.json` ignored,
 * neither package could ever commit the integrity-hashed graph, and `npm ci` - which refuses to run without a
 * lockfile - would stay unavailable. The suppression was removed; this keeps it removed.
 */
describe('.gitignore does not suppress npm lockfiles', () => {
  it('has no active rule naming package-lock.json', () => {
    const rules = readFileSync(join(REPOSITORY_ROOT, '.gitignore'), 'utf8')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0 && !line.startsWith('#'));

    expect(rules.filter((rule) => rule.includes('package-lock'))).toEqual([]);
  });
});

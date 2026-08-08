/**
 * Dependency-closure gate for the frontend and e2e npm packages.
 *
 * ## Subject
 *
 * `frontend/package.json` and `e2e/package.json` are the repository's only npm manifests, and neither
 * package commits a lockfile. A range specifier in either one therefore means a clean `npm install` may
 * resolve a package the suite has never been run against - which is how a compromised patch release
 * enters a project that looked pinned. This module asserts the two properties that stand in for the
 * lockfile that is absent:
 *
 * 1. every direct dependency of both manifests is an **exact** version, never a range; and
 * 2. every exact pin in `frontend/package.json` is the version actually present in
 *    `frontend/node_modules`, so a run can never report green while exercising a different graph from
 *    the one the repository declares.
 *
 * It is the Jest counterpart of `backend/tests/test_dependency_closure.py`, which does the same two
 * things for `backend/requirements-dev.txt`.
 *
 * ## What it deliberately does not assert
 *
 * The **transitive** graph. Without a lockfile there is no integrity-hashed reference to compare a
 * transitive tree against, and this module invents none: it would be asserting one uncontrolled tree
 * against another. That residual is real and is recorded rather than papered over - see the decision
 * log. It also makes no claim about `e2e/node_modules`, whose tree belongs to the Playwright runner
 * rather than to Jest; only that manifest's *shape* is checked here, because it is committed
 * configuration governed by the same finding.
 *
 * ## Scope
 *
 * Reads three files off disk and nothing else. It imports no application module, renders nothing and
 * opens no socket, so the msw interception the shared setup installs is never engaged.
 *
 * @see backend/tests/test_dependency_closure.py - the backend gate this mirrors.
 * @see docs/testing/DECISION-LOG.md - why exact pins plus a gate rather than a committed lockfile, and
 *   the residual that choice carries.
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

const frontendManifest = readManifest(join(FRONTEND_ROOT, 'package.json'));
const e2eManifest = readManifest(join(E2E_ROOT, 'package.json'));

const frontendDependencies = declaredDependencies(frontendManifest);
const e2eDependencies = declaredDependencies(e2eManifest);

/**
 * A guard, not a formality: every parametrised block below iterates a list read off disk, so an emptied,
 * renamed or restructured manifest would otherwise degenerate to zero cases and report green.
 */
describe('manifest parsing', () => {
  it('finds direct dependencies declared in frontend/package.json', () => {
    expect(frontendDependencies.length).toBeGreaterThan(0);
  });

  it('finds direct dependencies declared in e2e/package.json', () => {
    expect(e2eDependencies.length).toBeGreaterThan(0);
  });
});

describe('frontend/package.json declares exact versions only', () => {
  it.each(frontendDependencies.map((entry) => [`${entry.block}/${entry.name}`, entry] as const))(
    '%s is pinned exactly',
    (_label, entry) => {
      expect(entry.specifier).toMatch(EXACT_VERSION);
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
 * The installed-versus-declared half. Read from each package's own `package.json` inside
 * `node_modules` rather than through `require.resolve`, which would follow the `main` field and fail on
 * a package that exposes no entry point, and rather than through `npm ls`, which would mean spawning a
 * process from a test.
 */
describe('frontend/node_modules matches the manifest', () => {
  it.each(frontendDependencies.map((entry) => [entry.name, entry.specifier] as const))(
    '%s is installed at %s',
    (name, specifier) => {
      const installedPath = join(FRONTEND_ROOT, 'node_modules', name, 'package.json');

      let installed: Manifest;
      try {
        installed = readManifest(installedPath);
      } catch (error) {
        throw new Error(
          `${name} is pinned to ${specifier} in frontend/package.json and is not installed ` +
            `(${installedPath} is unreadable). Run: npm install --prefix frontend. ` +
            `Underlying error: ${String(error)}`,
        );
      }

      expect(installed.version).toBe(specifier);
    },
  );
});

/**
 * The rule whose absence lets the two properties above be enforced at all: with `package-lock.json`
 * ignored, neither package could ever commit the integrity-hashed graph, and `npm ci` - which refuses
 * to run without a lockfile - would stay unavailable. The suppression was removed; this keeps it
 * removed.
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

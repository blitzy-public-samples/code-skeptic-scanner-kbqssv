/**
 * The origin the end-to-end harness is served on, resolved once and imported by both
 * `e2e/vite.harness.config.ts` (which binds it) and `e2e/playwright.config.ts` (which
 * navigates to it and starts the server on it). Neither file computes a port of its own,
 * so the two can never disagree.
 *
 * Resolution order:
 *
 *   1. `HARNESS_PORT` - an explicit port, used verbatim.
 *   2. `E2E_PORT`     - the same thing under the name the CI job and `e2e/README.md`
 *                       use; accepted so one contract covers both spellings.
 *   3. `CLONE_INDEX`  - an offset added to {@link BASE_PORT}, so `CLONE_INDEX=002`
 *                       resolves to 4175.
 *   4. none set        - {@link BASE_PORT}.
 *
 * Several checkouts of this repository run concurrently on one host, each with its own
 * `CLONE_INDEX`, and a TCP port is host-global. `e2e/README.md` documents both variables.
 *
 * @see docs/testing/DECISION-LOG.md - section 4, the origin-resolution decision and its risks.
 */

/** Port used when neither environment variable is set. */
export const BASE_PORT = 4173;

/** Lowest port accepted, above the privileged range. */
const MIN_PORT = 1024;

/** Highest port accepted. */
const MAX_PORT = 65535;

/**
 * Loopback interface the harness binds. A literal address rather than `localhost`, which
 * resolves to either `127.0.0.1` or `::1` depending on the host's resolver order.
 */
export const HARNESS_HOST = '127.0.0.1';

/**
 * Reads a base-10 non-negative integer from the environment.
 *
 * @param name - Variable to read.
 * @returns The parsed value, or `null` when the variable is unset, empty, or not a
 *   base-10 non-negative integer. Leading zeros are accepted, so `'002'` reads as `2`.
 */
function readNonNegativeInteger(name: string): number | null {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === '') {
    return null;
  }

  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }

  const value = Number.parseInt(trimmed, 10);
  return Number.isSafeInteger(value) ? value : null;
}

/** Whether `candidate` is a port this module will hand out. */
function isUsablePort(candidate: number): boolean {
  return candidate >= MIN_PORT && candidate <= MAX_PORT;
}

/**
 * Resolves the port, applying the order in the module header. An out-of-range result from
 * either variable falls through to the next step rather than binding a port the harness
 * cannot serve on.
 */
function resolvePort(): number {
  for (const name of ['HARNESS_PORT', 'E2E_PORT']) {
    const explicitPort = readNonNegativeInteger(name);
    if (explicitPort !== null && isUsablePort(explicitPort)) {
      return explicitPort;
    }
  }

  const cloneIndex = readNonNegativeInteger('CLONE_INDEX');
  if (cloneIndex !== null && isUsablePort(BASE_PORT + cloneIndex)) {
    return BASE_PORT + cloneIndex;
  }

  return BASE_PORT;
}

/** Port the harness binds and Playwright navigates to. */
export const HARNESS_PORT = resolvePort();

/** Origin the harness is served on, the value of Playwright's `use.baseURL`. */
export const HARNESS_ORIGIN = `http://${HARNESS_HOST}:${HARNESS_PORT}`;

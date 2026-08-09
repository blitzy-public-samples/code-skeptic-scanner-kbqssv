/**
 * The per-test cleanup this layer owns, as a function any caller can invoke.
 *
 * `./setup-jest` registers {@link runSharedAfterEach} as the suite's single global `afterEach`, so this
 * module is what actually runs between the tests of every frontend suite. It is a separate module for one
 * reason: a contract that only a Jest hook can trigger can only be *observed* by comparing one test
 * against the next, which makes the proof depend on the order the tests are declared in. Exported as
 * functions, the same contract is provable inside a single test - mutate, clean, assert - and the hook
 * itself is then verified separately by checking what `./setup-jest` registers.
 *
 * Two functions, with one responsibility each:
 *
 * - {@link resetSharedTestState} discards every piece of mutable state this layer owns. Idempotent, and
 *   safe to call from a test.
 * - {@link runSharedAfterEach} is the hook body: it asserts the isolation ledger is empty and then resets,
 *   in a `finally`, so a failing test still hands the next one clean state.
 *
 * Nothing here registers a Jest hook, and importing this module has no side effect.
 *
 * @see frontend/src/test-utils/setup-jest.ts - the module that registers {@link runSharedAfterEach}.
 * @see frontend/src/test-utils/setup-jest.test.ts - the suite that holds both functions to this contract.
 * @see docs/testing/DECISION-LOG.md - rows D136 and D238.
 */

import { assertNoIsolationViolations, resetHandlerState } from './handlers';
import { server } from './msw-server';

/**
 * The environment variable `src/services/api.ts` reads once, at module scope, into the base URL it
 * prefixes every request with.
 *
 * It is absent from the environment the suite runs in, which is what makes that base the literal string
 * `undefined` - the shape `./handlers` screens against and the shape the service and component suites
 * assert. A test that assigns it does so to observe `api.ts` under a configured base, so cleanup
 * **deletes** the variable rather than restoring a previous value: there was none.
 */
export const BASE_URL_ENV_VAR = 'REACT_APP_API_BASE_URL';

/**
 * Discards every piece of mutable state this layer owns, returning it to the state a freshly started
 * worker has.
 *
 * Three things, and there is no fourth:
 *
 * 1. the msw runtime handler array, so a `server.use(...)` override cannot outlive the test that added it;
 * 2. every piece of `./handlers` module state - the request log and the isolation ledger - through the
 *    single `resetHandlerState()` entry point, so a new piece of state added there is discarded here
 *    without editing this function;
 * 3. {@link BASE_URL_ENV_VAR}.
 *
 * Absent from this list: the allowed-origin list, which is a frozen constant with no mutator; and anything
 * a suite installs for itself - `jest.spyOn`, `jest.mock`, fake timers - which each suite restores.
 *
 * Calling it twice in a row is indistinguishable from calling it once, so a test may clean up mid-body and
 * let the shared hook clean again afterwards.
 */
export function resetSharedTestState(): void {
  server.resetHandlers();
  resetHandlerState();
  delete process.env[BASE_URL_ENV_VAR];
}

/**
 * The body of the global `afterEach` that `./setup-jest` registers.
 *
 * Asserts the isolation ledger first and resets in a `finally`, and that order is the whole point: the
 * assertion is what fails the test that let a request escape - every caller in this codebase swallows the
 * error msw raises inside the request lifecycle - while the `finally` guarantees a test that fails for any
 * reason, including that one, still hands the next test clean state.
 *
 * @throws Error naming every recorded isolation breach, from {@link assertNoIsolationViolations}.
 */
export function runSharedAfterEach(): void {
  try {
    assertNoIsolationViolations();
  } finally {
    resetSharedTestState();
  }
}

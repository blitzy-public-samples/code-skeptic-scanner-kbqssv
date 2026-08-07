/**
 * Global Jest setup for the frontend suite.
 *
 * `frontend/jest.config.js` registers this module as the single entry in `setupFilesAfterEnv`, so Jest
 * loads it once per test file, after the test framework has been installed into the environment and before
 * that test file's own module body runs. That ordering is what makes the `afterEach` / `afterAll` globals
 * available at this module's top level - and it is also what lets interception start early enough, below.
 *
 * Three things are registered here, and nothing else:
 *
 * 1. `REACT_APP_API_BASE_URL` is removed from `process.env`. `frontend/src/services/api.ts` reads that
 *    variable once, at module scope, into the base URL it prefixes every request with, so with the variable
 *    unset the base is the literal string `undefined` - the shape the handlers in `./handlers` screen
 *    against and the shape the service and component suites assert. Removing it here makes that shape a
 *    property of the suite rather than of the shell the run was started from. No environment variable is
 *    ever assigned a value here.
 * 2. The `@testing-library/jest-dom` matchers on `expect` - `toBeInTheDocument`, `toHaveValue`,
 *    `toHaveTextContent` and the rest - which the component and page suites assert with.
 * 2. msw request interception over the `server` handle from `./msw-server`, started **synchronously while
 *    this module is evaluating**, not from `beforeAll`.
 * 3. A global `afterEach` that fails the test on any recorded isolation breach, then discards per-test
 *    handlers and every piece of mutable state this layer owns. This module is the single owner of that
 *    cleanup: `./handlers` registers no hook of its own, and its origin allow-list is frozen at module
 *    scope rather than reset, so there is no per-test origin state left to carry.
 *
 * ## Why interception starts at module scope
 *
 * `setupFilesAfterEnv` modules are evaluated before the test file is required, but `beforeAll` callbacks
 * do not run until after Jest has finished evaluating that file. Anything a test module does at *import*
 * time therefore happens in between. That window is real here: `src/services/api.ts` runs at module scope,
 * `src/components/Dashboard` and `src/components/TweetManagement` fetch on mount, and a suite that renders
 * or calls at module scope - or imports a module that does - would have issued a live request before
 * `server.listen()` had installed a single interceptor. `server.listen()` is synchronous, so calling it here
 * closes the window entirely. The teardown hooks stay as hooks, because there is nothing to tear down until
 * the tests have run.
 *
 * ## Why unhandled requests are recorded as well as reported
 *
 * `onUnhandledRequest` is a callback rather than the `'error'` string so that the request can be put in the
 * ledger in `./handlers` *before* `print.error()` raises. msw's own error is raised inside the request
 * lifecycle, and every caller in this codebase catches what it is handed - `getLatestTweets` and
 * `generateTweetResponse` re-throw a different error, `TweetList` logs and continues, `RealTimeFeed` logs -
 * so on its own it can be swallowed and the test can still pass. The ledger entry cannot be: the `afterEach`
 * below throws on it. `print.error()` is still called, so the request is reported and never performed.
 *
 * The module exports nothing and no test file imports it: Jest loads it by path, and it exists purely for
 * these side effects.
 *
 * Not registered here: the Chart.js canvas and resize-observer shims; any global replacement of, or spy
 * on, `console.error`, `console.warn`, `console.log` or `console.info`; global fake timers; an `alert`
 * stub; Testing Library global configuration; and any seeding of environment variables.
 *
 * @see frontend/src/test-utils/setup-jest.test.ts - the suite that holds this module to the contract above.
 * @see frontend/TESTING.md - the msw contract, the `server.use(...)` idiom, and how to add a handler.
 * @see docs/testing/DECISION-LOG.md section 3 - the decisions behind the settings and the omissions above.
 */

/*
 * Ahead of the imports below, and emitted ahead of them, so that no module reachable from this file can read
 * the variable before it is gone. `frontend/src/services/api.ts` reads it once, at module scope, into the
 * base URL it prefixes every request with; with the variable unset that base is the literal string
 * `undefined`, which is the shape `./handlers` screens against and the shape the suites assert. Removing it
 * here makes that shape a property of the suite rather than of the shell the run was started from.
 */
delete process.env.REACT_APP_API_BASE_URL;

import '@testing-library/jest-dom';

import { assertNoIsolationViolations, recordUnhandledRequest, resetHandlerState } from './handlers';
import { server } from './msw-server';

/*
 * Interception is live from this statement onward, which is before Jest evaluates the test file. Any request
 * a handler in `./handlers` does not cover reaches `onUnhandledRequest` instead of a socket.
 */
server.listen({
  onUnhandledRequest: (request, print) => {
    recordUnhandledRequest(request.method, request.url.href);
    // Reports the request and raises, so msw never performs it.
    print.error();
  },
});

/**
 * Fails the test on any isolation breach, then discards everything a test may have changed: the handlers it
 * added through `server.use(...)`, every piece of `./handlers` module state, and the base-URL variable.
 *
 * The assertion runs first and the resets run in `finally`, so a failing test still hands the next one clean
 * state. `resetHandlerState()` is the one call site for this file's state - the allowed-origin set, the
 * request log and the ledger - so a new piece of state added there is discarded here without editing this
 * hook. Resetting the ledger is what stops one test's breach from being attributed to a later one.
 *
 * `REACT_APP_API_BASE_URL` is deleted rather than restored: it is absent from the environment the suite runs
 * in, and a test that sets it does so to observe `services/api.ts` under a configured base URL.
 */
afterEach(() => {
  try {
    assertNoIsolationViolations();
  } finally {
    server.resetHandlers();
    resetHandlerState();
    delete process.env.REACT_APP_API_BASE_URL;
  }
});

afterAll(() => {
  server.close();
});

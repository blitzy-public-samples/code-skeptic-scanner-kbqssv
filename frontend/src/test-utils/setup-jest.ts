/**
 * Global Jest setup for the frontend suite.
 *
 * `frontend/jest.config.js` registers this module as the single entry in `setupFilesAfterEnv`, so Jest loads
 * it once per test file, after the test framework has been installed into the environment and before that
 * test file's own module body runs. That ordering is what makes the `afterEach` / `afterAll` globals available
 * at this module's top level.
 *
 * Four things are registered here, and nothing else:
 *
 * 1. `REACT_APP_API_BASE_URL` is **removed** from `process.env`, before the imports below and before any
 *    module reachable from this file can read it. `frontend/src/services/api.ts` reads that variable once, at
 *    module scope, into the base URL it prefixes every request with, so with the variable unset the base is
 *    the literal string `undefined` - the shape `./handlers` screens against and the shape the service and
 *    component suites assert. No environment variable is ever assigned a value here.
 * 2. The `@testing-library/jest-dom` matchers on `expect`.
 * 3. msw request interception over the `server` handle from `./msw-server`, started **synchronously while
 *    this module is evaluating**, not from `beforeAll`: Jest evaluates a test module - and every import-time
 *    side effect in its graph - before it runs `beforeAll`, and `services/api.ts` runs at module scope while
 *    both list components fetch on mount, so anything done at import time would otherwise reach a socket.
 * 4. A global `afterEach` that fails the test on any recorded isolation breach, then discards per-test
 *    handlers and every piece of mutable state this layer owns.
 *
 * `onUnhandledRequest` is a callback rather than the `'error'` string so the request can be put in the ledger
 * in `./handlers` *before* `print.error()` raises. The raise happens inside the request lifecycle and every
 * caller in this codebase loses it: `getLatestTweets` and `generateTweetResponse` log and rethrow a
 * *replacement* error, `TweetList` catches and logs, and `RealTimeFeed` catches nothing at all and leaves an
 * unhandled rejection. The ledger entry is what survives - the `afterEach` below throws on it.
 *
 * The module exports nothing and no test file imports it: Jest loads it by path, and it exists purely for
 * these side effects.
 *
 * Not registered here: the Chart.js canvas and resize-observer shims; any global replacement of, or spy on,
 * `console.error`, `console.warn`, `console.log` or `console.info`; global fake timers; an `alert` stub;
 * Testing Library global configuration; and any seeding of environment variables.
 *
 * @see frontend/src/test-utils/setup-jest.test.ts - the suite that holds this module to the contract above.
 * @see frontend/TESTING.md - the msw contract, the `server.use(...)` idiom, and how to add a handler.
 * @see docs/testing/DECISION-LOG.md - rows D108 and D136.
 */

/*
 * Emitted ahead of the imports below, so no module reachable from this file can read the variable before it
 * is gone. See item 1 in the module docstring.
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
 * state. `resetHandlerState()` is the one call site for that state - the request log and the ledger - so a new
 * piece of state added there is discarded here without editing this hook.
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

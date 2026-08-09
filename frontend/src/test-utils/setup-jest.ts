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
 * 4. A global `afterEach` bound to `runSharedAfterEach` from `./reset-shared-state`, which fails the test
 *    on any recorded isolation breach and then discards per-test handlers and every piece of mutable state
 *    this layer owns. The body lives in that module rather than inline here so a test can invoke the same
 *    cleanup directly and prove the contract without depending on the order tests are declared in.
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
 * @see frontend/src/test-utils/reset-shared-state.ts - the cleanup this file registers.
 * @see frontend/TESTING.md - the msw contract, the `server.use(...)` idiom, and how to add a handler.
 * @see docs/testing/DECISION-LOG.md - rows D108, D136 and D238.
 */

/*
 * Emitted ahead of the imports below, so no module reachable from this file can read the variable before it
 * is gone. See item 1 in the module docstring.
 */
delete process.env.REACT_APP_API_BASE_URL;

import '@testing-library/jest-dom';

import { recordUnhandledRequest } from './handlers';
import { server } from './msw-server';
import { runSharedAfterEach } from './reset-shared-state';

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

/*
 * The hook body is `runSharedAfterEach` itself, passed by reference rather than wrapped in an arrow
 * function: `./setup-jest.test.ts` asserts that identity, which is how the wiring between this file and the
 * cleanup is proven without one test having to observe the state another test left behind.
 *
 * What it does - assert the isolation ledger, then discard the handlers a test added with `server.use(...)`,
 * every piece of `./handlers` module state and the base-URL variable, with the resets in a `finally` - is
 * documented on the function in `./reset-shared-state`.
 */
afterEach(runSharedAfterEach);

afterAll(() => {
  server.close();
});

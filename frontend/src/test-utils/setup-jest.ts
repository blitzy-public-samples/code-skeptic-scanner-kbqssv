/**
 * Global Jest setup for the frontend suite: the single `setupFilesAfterEnv` entry in
 * `frontend/jest.config.js`, loaded once per test file after the test framework is installed and before that
 * test file's own module body runs - the ordering that makes `afterEach` and `afterAll` available at this
 * module's top level.
 *
 * Three orderings this file guarantees, each load-bearing:
 *
 * 1. `REACT_APP_API_BASE_URL` is **removed** from `process.env` ahead of the imports below, so no module
 *    reachable from this file can read it. `frontend/src/services/api.ts` reads it once, at module scope,
 *    into the base URL it prefixes every request with, so with the variable unset that base is the literal
 *    string `undefined` - the shape `./handlers` screens against and the shape the service and component
 *    suites assert.
 * 2. msw interception over the `server` handle from `./msw-server` starts **synchronously while this module
 *    is evaluating**, not from `beforeAll`. Jest evaluates a test module, and every import-time side effect
 *    in its graph, before it runs `beforeAll`, and `services/api.ts` runs at module scope while both list
 *    components fetch on mount - so an import-time request would otherwise reach a socket.
 * 3. The global `afterEach` fails the test on any recorded isolation breach **before** it discards per-test
 *    handlers and the mutable state this layer owns.
 *
 * `onUnhandledRequest` records the request in the ledger in `./handlers` before `print.error()` raises,
 * because the raise happens inside the request lifecycle, where every caller in this codebase loses it: the
 * two services rethrow a replacement error, `TweetList` catches and logs, and `RealTimeFeed` leaves an
 * unhandled rejection. The ledger entry is what survives to fail the test.
 *
 * @see frontend/src/test-utils/setup-jest.test.ts - the suite that holds this module to the contract above.
 * @see frontend/src/test-utils/reset-shared-state.ts - the cleanup this file registers.
 * @see frontend/TESTING.md - the msw contract, the `server.use(...)` idiom, and how to add a handler.
 * @see docs/testing/DECISION-LOG.md - rows D108, D136, D238 and D344.
 */

/* Ahead of the imports below, so no module reachable from this file can read the variable before it is gone. */
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
 * `runSharedAfterEach` is passed by reference, not wrapped: `./setup-jest.test.ts` asserts that identity.
 * Its body - assert the isolation ledger, then reset the per-test handlers, `./handlers` module state and the
 * base-URL variable in a `finally` - is documented on the function in `./reset-shared-state`.
 */
afterEach(runSharedAfterEach);

afterAll(() => {
  server.close();
});

/**
 * Global Jest setup for the frontend suite.
 *
 * `frontend/jest.config.js` registers this module as the single entry in `setupFilesAfterEnv`, so Jest
 * loads it once per test file, after the test framework has been installed into the environment and before
 * that test file's own module body runs. That ordering is what makes the `beforeAll` / `afterEach` /
 * `afterAll` globals available at this module's top level.
 *
 * Two things are registered here, and nothing else:
 *
 * 1. The `@testing-library/jest-dom` matchers on `expect` - `toBeInTheDocument`, `toHaveValue`,
 *    `toHaveTextContent` and the rest - which the component and page suites assert with.
 * 2. The msw request-interception lifecycle around the `server` handle from `./msw-server`: interception
 *    starts before a file's first test, per-test overrides installed with `server.use(...)` are discarded
 *    after each test, and interception is torn down after the last test.
 *
 * Interception runs with `onUnhandledRequest: 'error'`, so a request that no handler in `./handlers` covers
 * fails the test that emitted it instead of reaching a socket. Discarding overrides after every test keeps
 * a handler installed for one test from changing the outcome - or the attribution - of any later one.
 *
 * The module exports nothing and no test file imports it: Jest loads it by path, and it exists purely for
 * these side effects.
 *
 * Deliberately absent, listed so that a later change does not reinstate them by accident. Each is recorded
 * in `docs/testing/DECISION-LOG.md`, which names the exact packages and globals involved:
 *
 * - the Chart.js canvas and resize-observer shims;
 * - any global replacement of, or spy on, `console.error`, `console.warn`, `console.log` or `console.info`;
 * - global fake timers, an `alert` stub, Testing Library global configuration, and any seeding of
 *   environment variables - each of which belongs to the individual suite that needs it, if any does.
 *
 * @see frontend/TESTING.md - the msw contract, the `server.use(...)` idiom, and how to add a handler.
 * @see docs/testing/DECISION-LOG.md - the decisions behind the settings and the omissions above.
 */

import '@testing-library/jest-dom';

import { server } from './msw-server';

/**
 * Starts msw interception for the current test file, with any request the default handlers do not cover
 * treated as a failure rather than passed through to the network.
 */
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

/**
 * Restores the default handler array after every test, discarding whatever that test added through
 * `server.use(...)`.
 */
afterEach(() => {
  server.resetHandlers();
});

/**
 * Stops interception once the file's last test has finished, releasing the request interceptors msw
 * installed.
 */
afterAll(() => {
  server.close();
});

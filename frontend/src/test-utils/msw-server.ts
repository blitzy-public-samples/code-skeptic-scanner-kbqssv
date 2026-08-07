/**
 * The msw server handle for the frontend Jest suites: one `setupServer` instance over the default handler
 * array from `./handlers`. A suite imports `{ server }` to add a one-off route for a single test, pairing
 * it with `rest` imported from `'msw'` directly.
 *
 * This module constructs that handle and does nothing else. It starts and stops no interception, registers
 * no Jest hook and defines no request handler, so importing it has no side effect. The lifecycle - starting
 * interception, discarding per-test overrides between tests, and tearing it all down at the end - belongs
 * to `src/test-utils/setup-jest.ts`, which `jest.config.js` registers through `setupFilesAfterEnv`.
 *
 * See `frontend/TESTING.md` for the msw contract and the override idiom.
 *
 * msw 1.x API - `setupServer` comes from `'msw/node'` and takes its handlers as individual arguments,
 * hence the spread at the call site.
 */

import { setupServer } from 'msw/node';

import { handlers } from './handlers';

/**
 * The single msw interceptor every suite in a test file shares. Jest gives each test file its own module
 * registry, so one instance exists per file and every import inside that file resolves to it.
 */
export const server = setupServer(...handlers);

/**
 * The msw server handle for the frontend Jest suites: one `setupServer` instance over the default
 * handler array from `./handlers`, which a suite extends for a single test with `server.use(...)`.
 *
 * Constructing the handle is all this module does - no interception is started and no Jest hook is
 * registered, so importing it has no side effect. `src/test-utils/setup-jest.ts` owns the
 * lifecycle. msw 1.x takes its handlers as individual arguments, hence the spread.
 */

import { setupServer } from 'msw/node';

import { handlers } from './handlers';

export const server = setupServer(...handlers);

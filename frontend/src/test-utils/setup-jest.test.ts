/**
 * The suite that holds `./setup-jest` to the per-test isolation contract it documents.
 *
 * `frontend/jest.config.js` registers `./setup-jest` as its single `setupFilesAfterEach` entry, so that
 * module's `afterEach` runs between the tests below exactly as it runs between the tests of every other
 * suite. Each pair of tests here therefore measures the shared hook rather than anything this file installs:
 * the first test of a pair changes one piece of state a real suite is allowed to change, and the second
 * asserts the change is gone - by reading the state back and by emitting the request whose outcome the
 * change would have altered.
 *
 * **The tests in each pair are ordered on purpose and must stay in this order.** Jest runs the tests of a
 * file in declaration order, and a pair whose members were reordered, split across files, or run in
 * isolation would pass without measuring anything. The four pieces of state, in the order the pairs appear:
 *
 * | State                                    | Changed by                        | Reset by                      |
 * |------------------------------------------|-----------------------------------|-------------------------------|
 * | isolation ledger (`./handlers`)          | any un-handled or screened request| `resetIsolationViolations()`  |
 * | msw runtime handler array                | `server.use(handler)`             | `server.resetHandlers()`      |
 * | request log (`./handlers`)               | any intercepted request           | `resetRecordedRequests()`     |
 * | `process.env.REACT_APP_API_BASE_URL`     | an assignment inside a test       | `delete` in the shared hook   |
 *
 * The allowed-origin list is deliberately absent from that table: it is a frozen constant with no mutator,
 * and the first pair below is what proves it - a request to a non-loopback origin matches no handler at all.
 *
 * Nothing here mocks a module, so every request below is answered by the real handler array over the real
 * msw interceptor.
 *
 * @see frontend/src/test-utils/setup-jest.ts - the module under test.
 * @see frontend/src/test-utils/handlers.ts - the handler array, the origin scoping and the request log.
 * @see docs/testing/DECISION-LOG.md - rows D103 and D136.
 */

import axios from 'axios';
import { rest } from 'msw';

import {
  ALLOWED_REQUEST_ORIGINS,
  acknowledgeIsolationViolations,
  allowedRequestOrigins,
  lastRecordedRequest,
  makeDefaultTweetsJson,
  recordedIsolationViolations,
  recordedRequests,
} from './handlers';
import { server } from './msw-server';
import { fetchTweets } from '../services/api';

/** The two origins `./handlers` registers every pattern under. */
const DEFAULT_ORIGINS = ['http://localhost', 'http://127.0.0.1'];

/** An absolute origin no handler answers. Resolves to nothing; nothing dials it. */
const REMOTE_ORIGIN = 'https://api.example.test';

/** A request whose path a handler would match, addressed to {@link REMOTE_ORIGIN}. */
const REMOTE_TWEETS_URL = `${REMOTE_ORIGIN}/tweets?page=1&limit=10`;

/** Base URL `services/api.ts` builds when `REACT_APP_API_BASE_URL` is unset, as it reaches msw. */
const UNSET_BASE = 'http://localhost/undefined';

/**
 * Issues a request without letting axios reject on a non-2xx status, so a screened-out request can be
 * asserted on its status and body rather than on an error message that has lost both.
 */
async function get(url: string): Promise<{ status: number; data: unknown }> {
  const response = await axios.get(url, { validateStatus: () => true });
  return { status: response.status, data: response.data };
}

describe('shared setup: the allowed-origin list is frozen', () => {
  it('answers only the two loopback origins, and exposes no way to add a third', () => {
    expect(allowedRequestOrigins()).toEqual(DEFAULT_ORIGINS);
    expect(Object.isFrozen(ALLOWED_REQUEST_ORIGINS)).toBe(true);
    expect(() => {
      (ALLOWED_REQUEST_ORIGINS as string[]).push(REMOTE_ORIGIN);
    }).toThrow(TypeError);
    expect(allowedRequestOrigins()).toEqual(DEFAULT_ORIGINS);
  });

  it('leaves a request to any other origin unmatched, ledgered and never performed', async () => {
    // msw reports an unhandled request through the callback `./setup-jest` installs, which appends to the
    // ledger and then raises inside the request lifecycle; silenced for this test only so the reported
    // request does not drown the output, and asserted on rather than discarded.
    const consoleWarn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    try {
      await expect(get(REMOTE_TWEETS_URL)).rejects.toBeDefined();

      // No handler ran, so nothing reached the request log.
      expect(recordedRequests()).toEqual([]);

      const ledgered = recordedIsolationViolations();

      expect(ledgered).toHaveLength(1);
      expect(ledgered[0]).toMatchObject({ kind: 'unhandled-request', handler: '(no handler)' });
      expect(ledgered[0].url).toContain(REMOTE_ORIGIN);
      expect(ledgered[0].violations[0]).toContain(DEFAULT_ORIGINS.join(' and '));

      // The shared `afterEach` throws on the ledger. This test provoked the breach deliberately and has
      // just asserted on it, so it takes it off the ledger rather than letting it fail the test. Every
      // other test leaves the ledger alone.
      expect(acknowledgeIsolationViolations()).toHaveLength(1);
    } finally {
      consoleError.mockRestore();
      consoleWarn.mockRestore();
    }
  });

  it('starts the next test with an empty ledger', () => {
    expect(recordedIsolationViolations()).toEqual([]);
    expect(allowedRequestOrigins()).toEqual(DEFAULT_ORIGINS);
  });
});

describe('shared setup: the msw runtime handler array', () => {
  it('serves the override the test installs', async () => {
    server.use(rest.get('*/tweets', (_req, res, ctx) => res(ctx.status(200), ctx.json([]))));

    await expect(fetchTweets(1, 1)).resolves.toEqual([]);
  });

  it('serves the default handlers again in the next test', async () => {
    await expect(fetchTweets(1, 1)).resolves.toEqual(makeDefaultTweetsJson());
  });
});

describe('shared setup: the request log', () => {
  it('records the requests a test emits', async () => {
    await fetchTweets(2, 10);
    await fetchTweets(3, 10);

    expect(recordedRequests()).toHaveLength(2);
  });

  it('starts the next test with an empty log', () => {
    expect(recordedRequests()).toEqual([]);
    expect(lastRecordedRequest()).toBeUndefined();
  });
});

describe('shared setup: REACT_APP_API_BASE_URL', () => {
  it('is absent from the environment the suite runs in', () => {
    expect(process.env.REACT_APP_API_BASE_URL).toBeUndefined();
    expect('REACT_APP_API_BASE_URL' in process.env).toBe(false);
  });

  it('leaves services/api.ts prefixing every request with the literal string "undefined"', async () => {
    await fetchTweets(2, 10);

    expect(lastRecordedRequest()).toMatchObject({
      base: UNSET_BASE,
      url: `${UNSET_BASE}/tweets?page=2&limit=10`,
      query: { page: '2', limit: '10' },
      violations: [],
      status: 200,
    });
  });

  it('can be given a value by a test that installs a handler for that exact URL', async () => {
    // The frozen allow-list covers loopback only, so driving an absolute non-loopback base URL means
    // registering a handler for it - which is the documented remedy and the only one.
    const seen: string[] = [];
    server.use(
      rest.get(`${REMOTE_ORIGIN}/tweets`, (req, res, ctx) => {
        seen.push(req.url.href);
        return res(ctx.status(200), ctx.json([]));
      }),
    );

    process.env.REACT_APP_API_BASE_URL = REMOTE_ORIGIN;

    jest.resetModules();
    const configured = (await import('../services/api')) as typeof import('../services/api');

    await expect(configured.fetchTweets(2, 10)).resolves.toEqual([]);
    expect(seen).toEqual([`${REMOTE_ORIGIN}/tweets?page=2&limit=10`]);

    // The suite's own handler answered it, so no module handler recorded it and nothing was ledgered.
    expect(recordedRequests()).toEqual([]);
    expect(recordedIsolationViolations()).toEqual([]);
  });

  it('is unset again in the next test, which reloads the same subject and gets "undefined" back', async () => {
    expect(process.env.REACT_APP_API_BASE_URL).toBeUndefined();

    jest.resetModules();
    const reloaded = (await import('../services/api')) as typeof import('../services/api');
    await reloaded.fetchTweets(2, 10);

    expect(lastRecordedRequest()).toMatchObject({
      base: UNSET_BASE,
      origin: 'http://localhost',
      violations: [],
      status: 200,
    });
  });
});

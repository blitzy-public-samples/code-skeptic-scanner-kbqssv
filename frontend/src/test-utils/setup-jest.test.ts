/**
 * The suite that holds `./setup-jest` to the per-test isolation contract it documents.
 *
 * `frontend/jest.config.js` registers `./setup-jest` as its single `setupFilesAfterEnv` entry, so that
 * module's `afterEach` runs between the tests below exactly as it runs between the tests of every other
 * suite. Each pair of tests here therefore measures the shared hook rather than anything this file
 * installs: the first test of a pair changes one piece of state that a real suite is allowed to change, and
 * the second test asserts that the change is gone - by reading the state back and by emitting the request
 * whose outcome the change would have altered.
 *
 * **The tests in each pair are ordered on purpose and must stay in this order.** Jest runs the tests of a
 * file in declaration order, and a pair whose members were reordered, split across files, or run in
 * isolation would pass without measuring anything. The four pieces of state, in the order the pairs appear:
 *
 * | State                                    | Changed by                        | Reset by                      |
 * |------------------------------------------|-----------------------------------|-------------------------------|
 * | allowed-origin list (`./handlers`)       | `allowRequestOrigin(origin)`      | `resetAllowedRequestOrigins()`|
 * | msw runtime handler array                | `server.use(handler)`             | `server.resetHandlers()`      |
 * | request log (`./handlers`)               | any intercepted request           | `resetRecordedRequests()`     |
 * | `process.env.REACT_APP_API_BASE_URL`     | an assignment inside a test       | `delete` in the shared hook   |
 *
 * Nothing here mocks a module, so every request below is answered by the real handler array over the real
 * msw interceptor, and the statuses asserted are the ones a mis-scoped opt-in would silently turn into a
 * 200.
 *
 * @see frontend/src/test-utils/setup-jest.ts - the module under test.
 * @see frontend/src/test-utils/handlers.ts - the handler array, the origin screening and the request log.
 */

import axios from 'axios';
import { rest } from 'msw';

import {
  CONTRACT_VIOLATION_DETAIL,
  CONTRACT_VIOLATION_STATUS,
  acknowledgeIsolationViolations,
  allowRequestOrigin,
  allowedRequestOrigins,
  lastRecordedRequest,
  makeDefaultTweetsJson,
  recordedRequests,
} from './handlers';
import type { ContractViolationBody } from './handlers';
import { server } from './msw-server';
import { fetchTweets } from '../services/api';

/** The two origins `./handlers` answers when nothing has opted into another one. */
const DEFAULT_ORIGINS = ['http://localhost', 'http://127.0.0.1'];

/** An absolute origin no handler answers until a test admits it. Resolves to nothing; nothing dials it. */
const REMOTE_ORIGIN = 'https://api.example.test';

/** A request the tweet-collection handler matches, addressed to {@link REMOTE_ORIGIN}. */
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

describe('shared setup: the allowed-origin list', () => {
  it('answers an absolute origin for the test that admits it', async () => {
    allowRequestOrigin(REMOTE_ORIGIN);

    expect(allowedRequestOrigins()).toEqual([...DEFAULT_ORIGINS, REMOTE_ORIGIN]);

    const { status } = await get(REMOTE_TWEETS_URL);

    expect(status).toBe(200);
    expect(lastRecordedRequest()).toMatchObject({
      handler: 'GET */tweets',
      origin: REMOTE_ORIGIN,
      violations: [],
      status: 200,
    });
  });

  it('has forgotten that origin by the next test, which is screened out instead of mocked', async () => {
    expect(allowedRequestOrigins()).toEqual(DEFAULT_ORIGINS);

    // The handler writes the violation here as well, so a caller that swallows the rejection still leaves a
    // trace; silenced for the duration of this test only, and asserted on rather than discarded.
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    try {
      const { status, data } = await get(REMOTE_TWEETS_URL);

      expect(status).toBe(CONTRACT_VIOLATION_STATUS);

      const body = data as ContractViolationBody;
      expect(body.detail).toBe(CONTRACT_VIOLATION_DETAIL);
      expect(body.violations).toEqual([
        `origin "${REMOTE_ORIGIN}" is not an allowed test origin (${DEFAULT_ORIGINS.join(', ')})`,
      ]);

      expect(consoleError).toHaveBeenCalledTimes(1);
      expect(String(consoleError.mock.calls[0][0])).toContain(REMOTE_ORIGIN);

      // The screening also lands in the isolation ledger, which the shared `afterEach` throws on. This
      // test provoked that breach deliberately and has just asserted on it, so it takes it off the ledger
      // rather than letting it fail the test. Every other test leaves the ledger alone.
      const acknowledged = acknowledgeIsolationViolations();

      expect(acknowledged).toHaveLength(1);
      expect(acknowledged[0]).toMatchObject({ kind: 'origin', handler: 'GET */tweets' });
    } finally {
      consoleError.mockRestore();
    }
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

  it('can be given a value by a test that reloads its subject in isolation', async () => {
    process.env.REACT_APP_API_BASE_URL = REMOTE_ORIGIN;
    allowRequestOrigin(REMOTE_ORIGIN);

    jest.resetModules();
    const configured = (await import('../services/api')) as typeof import('../services/api');
    await configured.fetchTweets(2, 10);

    expect(lastRecordedRequest()).toMatchObject({
      base: REMOTE_ORIGIN,
      url: `${REMOTE_ORIGIN}/tweets?page=2&limit=10`,
      origin: REMOTE_ORIGIN,
      violations: [],
      status: 200,
    });
  });

  it('is unset again in the next test, which reloads the same subject and gets "undefined" back', async () => {
    expect(process.env.REACT_APP_API_BASE_URL).toBeUndefined();
    expect(allowedRequestOrigins()).toEqual(DEFAULT_ORIGINS);

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

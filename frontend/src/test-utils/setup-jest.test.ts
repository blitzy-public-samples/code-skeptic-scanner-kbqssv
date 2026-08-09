/**
 * The suite that holds `./setup-jest` and `./reset-shared-state` to the per-test isolation contract they
 * document.
 *
 * **No test here depends on another, and none may.** The contract under test is "state a test changes is
 * gone before the next test sees it", and the obvious way to check that - change something in one test and
 * look for it in the next - makes the proof depend on the order the tests are declared in, so a reordered,
 * split or individually-run pair passes while measuring nothing. `./reset-shared-state` exists so the same
 * contract is provable inside a single test instead: each test below **changes** one piece of state,
 * **calls the shared cleanup**, and then **asserts the change is gone** - by reading the state back, and by
 * emitting the request whose outcome the change would have altered. The shared `afterEach` then runs the
 * same cleanup again, which is harmless because it is idempotent.
 *
 * That leaves one thing a single test cannot see: whether `./setup-jest` actually registers that cleanup.
 * The last `describe` covers it directly, by loading `./setup-jest` into an isolated module registry with
 * the Jest hook globals captured, and asserting what it handed them.
 *
 * The four pieces of state, and what discards each:
 *
 * | State                                    | Changed by                         | Reset by                     |
 * |------------------------------------------|------------------------------------|------------------------------|
 * | isolation ledger (`./handlers`)          | any un-handled or screened request | `resetSharedTestState()`     |
 * | msw runtime handler array                | `server.use(handler)`              | `resetSharedTestState()`     |
 * | request log (`./handlers`)               | any intercepted request            | `resetSharedTestState()`     |
 * | `process.env.REACT_APP_API_BASE_URL`     | an assignment inside a test        | `resetSharedTestState()`     |
 *
 * The allowed-origin list is deliberately absent from that table: it is a frozen constant with no mutator,
 * and the first test below is what proves it - a request to a non-loopback origin matches no handler at all.
 *
 * Nothing here mocks a module except in the wiring test's isolated registry, so every request below is
 * answered by the real handler array over the real msw interceptor.
 *
 * @see frontend/src/test-utils/setup-jest.ts - the module that registers the hook.
 * @see frontend/src/test-utils/reset-shared-state.ts - the cleanup under test.
 * @see frontend/src/test-utils/handlers.ts - the handler array, the origin scoping and the request log.
 * @see docs/testing/DECISION-LOG.md - rows D103, D136 and D238.
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
import * as resetSharedState from './reset-shared-state';
import { BASE_URL_ENV_VAR, resetSharedTestState, runSharedAfterEach } from './reset-shared-state';
import { fetchTweets } from '../services/api';

/** The two origins `./handlers` registers every pattern under. */
const DEFAULT_ORIGINS = ['http://localhost', 'http://127.0.0.1'];

/** An absolute origin no handler answers. Resolves to nothing; nothing dials it. */
const REMOTE_ORIGIN = 'https://api.example.test';

/** A request whose path a handler would match, addressed to {@link REMOTE_ORIGIN}. */
const REMOTE_TWEETS_URL = `${REMOTE_ORIGIN}/tweets?page=1&limit=10`;

/** Base URL `services/api.ts` builds when `REACT_APP_API_BASE_URL` is unset, as it reaches msw. */
const UNSET_BASE = 'http://localhost/undefined';

/** A loopback URL no handler in `./handlers` covers, used only by the import-time probe below. */
const IMPORT_TIME_PROBE_URL = 'http://localhost/import-time-probe';

/** The body the import-time probe's own handler answers with, so the answer is unambiguously its. */
const IMPORT_TIME_PROBE_BODY = { intercepted: 'at module evaluation' };

/*
 * The probe's handler, registered while this module is being evaluated. It is deliberately **not** one of
 * the module handlers: those record into `./handlers`' request log, and an entry created at module scope
 * would still be there for whichever test ran first - which is the order dependence this suite exists
 * without. Answering from a suite-local handler on a path no contract names keeps every shared collection
 * empty. `resetSharedTestState()` discards this handler at the first cleanup, by which time the probe has
 * long settled.
 */
server.use(
  rest.get(IMPORT_TIME_PROBE_URL, (_req, res, ctx) =>
    res(ctx.status(200), ctx.json(IMPORT_TIME_PROBE_BODY)),
  ),
);

/**
 * The outcome of a request issued **while this module is still being evaluated**, before Jest has run a
 * single hook of this file or of `./setup-jest`.
 *
 * `./setup-jest` calls `server.listen(...)` synchronously as it is evaluated rather than from `beforeAll`,
 * precisely so a request in this position is intercepted. The settled outcome is captured here and asserted
 * in the first test below, which makes the proof independent of which test runs first - and of whether that
 * test runs at all, since the rejection branch is folded into the value rather than left to reject.
 * Without interception this settles as an `AxiosError` from a real socket attempt.
 */
const importTimeProbe: Promise<{ status: number; data: unknown } | { error: string }> = axios
  .get(IMPORT_TIME_PROBE_URL, { validateStatus: () => true })
  .then((response) => ({ status: response.status, data: response.data as unknown }))
  .catch((error: unknown) => ({ error: error instanceof Error ? error.message : String(error) }));

/**
 * Issues a request without letting axios reject on a non-2xx status, so a screened-out request can be
 * asserted on its status and body rather than on an error message that has lost both.
 */
async function get(url: string): Promise<{ status: number; data: unknown }> {
  const response = await axios.get(url, { validateStatus: () => true });
  return { status: response.status, data: response.data };
}

describe('shared setup: interception is live before the first hook runs', () => {
  it('answered a request issued while this test module was still being evaluated', async () => {
    // An escape would surface here as `{ error: 'Network Error' }` rather than a response.
    await expect(importTimeProbe).resolves.toEqual({
      status: 200,
      data: IMPORT_TIME_PROBE_BODY,
    });
  });

  it('left no trace of the probe in any shared collection', async () => {
    await importTimeProbe;

    // The probe was answered by its own handler, so no module handler recorded it and nothing was ledgered -
    // which is what lets every test in this file assert an empty log or ledger while running alone.
    expect(recordedRequests()).toEqual([]);
    expect(recordedIsolationViolations()).toEqual([]);
  });
});

describe('shared setup: the allowed-origin list is frozen', () => {
  it('answers only the two loopback origins, and exposes no way to add a third', () => {
    expect(allowedRequestOrigins()).toEqual(DEFAULT_ORIGINS);
    expect(Object.isFrozen(ALLOWED_REQUEST_ORIGINS)).toBe(true);
    expect(() => {
      (ALLOWED_REQUEST_ORIGINS as string[]).push(REMOTE_ORIGIN);
    }).toThrow(TypeError);
    expect(allowedRequestOrigins()).toEqual(DEFAULT_ORIGINS);
  });
});

describe('shared setup: the isolation ledger', () => {
  it('ledgers a request to any other origin, never performs it, and the cleanup empties the ledger', async () => {
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

      // The contract: the shared cleanup discards the ledger. Asserted here rather than by a following
      // test, so this proof does not depend on declaration order.
      resetSharedTestState();

      expect(recordedIsolationViolations()).toEqual([]);
      expect(allowedRequestOrigins()).toEqual(DEFAULT_ORIGINS);
    } finally {
      // The ledger is already empty, so the shared `afterEach` has nothing to raise on. Drained anyway so
      // this test cannot fail through the hook if an assertion above threw before the reset.
      acknowledgeIsolationViolations();
      consoleError.mockRestore();
      consoleWarn.mockRestore();
    }
  });

  it('is emptied even when the ledger assertion throws, so the next test starts clean', async () => {
    const consoleWarn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    try {
      await expect(get(REMOTE_TWEETS_URL)).rejects.toBeDefined();
      expect(recordedIsolationViolations()).toHaveLength(1);

      // The hook body, invoked exactly as the shared `afterEach` invokes it. It must raise on the breach
      // *and* still reset - the assertion is in a `try`, the cleanup in the `finally`.
      expect(() => runSharedAfterEach()).toThrow(/breached test isolation/);

      expect(recordedIsolationViolations()).toEqual([]);
      expect(recordedRequests()).toEqual([]);
    } finally {
      acknowledgeIsolationViolations();
      consoleError.mockRestore();
      consoleWarn.mockRestore();
    }
  });
});

describe('shared setup: the msw runtime handler array', () => {
  it('serves the override the test installs, and the cleanup restores the default handlers', async () => {
    server.use(rest.get('*/tweets', (_req, res, ctx) => res(ctx.status(200), ctx.json([]))));

    await expect(fetchTweets(1, 1)).resolves.toEqual([]);

    resetSharedTestState();

    await expect(fetchTweets(1, 1)).resolves.toEqual(makeDefaultTweetsJson());
  });
});

describe('shared setup: the request log', () => {
  it('records the requests a test emits, and the cleanup empties the log', async () => {
    await fetchTweets(2, 10);
    await fetchTweets(3, 10);

    expect(recordedRequests()).toHaveLength(2);

    resetSharedTestState();

    expect(recordedRequests()).toEqual([]);
    expect(lastRecordedRequest()).toBeUndefined();
  });
});

describe(`shared setup: ${BASE_URL_ENV_VAR}`, () => {
  it('is absent from the environment the suite runs in', () => {
    expect(process.env[BASE_URL_ENV_VAR]).toBeUndefined();
    expect(BASE_URL_ENV_VAR in process.env).toBe(false);
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

  it('can be given a value by a test, and the cleanup removes it again', async () => {
    // The frozen allow-list covers loopback only, so driving an absolute non-loopback base URL means
    // registering a handler for it - which is the documented remedy and the only one.
    const seen: string[] = [];
    server.use(
      rest.get(`${REMOTE_ORIGIN}/tweets`, (req, res, ctx) => {
        seen.push(req.url.href);
        return res(ctx.status(200), ctx.json([]));
      }),
    );

    process.env[BASE_URL_ENV_VAR] = REMOTE_ORIGIN;

    jest.resetModules();
    const configured = (await import('../services/api')) as typeof import('../services/api');

    await expect(configured.fetchTweets(2, 10)).resolves.toEqual([]);
    expect(seen).toEqual([`${REMOTE_ORIGIN}/tweets?page=2&limit=10`]);

    // The suite's own handler answered it, so no module handler recorded it and nothing was ledgered.
    expect(recordedRequests()).toEqual([]);
    expect(recordedIsolationViolations()).toEqual([]);

    resetSharedTestState();

    expect(process.env[BASE_URL_ENV_VAR]).toBeUndefined();
    expect(BASE_URL_ENV_VAR in process.env).toBe(false);

    // Reloaded against the cleaned environment, the same subject is back on the literal `undefined` base -
    // and the override handler that answered the remote origin is gone with it.
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

describe('shared setup: the hook setup-jest registers', () => {
  /**
   * Loads `./setup-jest` into an isolated module registry with the Jest hook globals replaced by captures,
   * so what it registers can be read back rather than inferred.
   *
   * `./msw-server` is mocked for the duration so the live interceptor every other suite depends on is
   * untouched - the isolated copy of `./setup-jest` calls `listen` and its `afterAll` calls `close` on the
   * stand-in. `./reset-shared-state` is mapped to *this* file's already-imported instance, so the captured
   * hook can be compared by identity against {@link runSharedAfterEach}.
   */
  function loadSetupJestWithCapturedHooks(): {
    afterEachCallbacks: unknown[];
    afterAllCallbacks: Array<() => void>;
    listen: jest.Mock;
    close: jest.Mock;
  } {
    const afterEachCallbacks: unknown[] = [];
    const afterAllCallbacks: Array<() => void> = [];
    const listen = jest.fn();
    const close = jest.fn();

    const realAfterEach = global.afterEach;
    const realAfterAll = global.afterAll;

    try {
      (global as unknown as { afterEach: unknown }).afterEach = (callback: unknown) => {
        afterEachCallbacks.push(callback);
      };
      (global as unknown as { afterAll: unknown }).afterAll = (callback: () => void) => {
        afterAllCallbacks.push(callback);
      };

      jest.isolateModules(() => {
        jest.doMock('./msw-server', () => ({ server: { listen, close, resetHandlers: jest.fn() } }));
        jest.doMock('./reset-shared-state', () => resetSharedState);
        // eslint-disable-next-line global-require
        require('./setup-jest');
      });
    } finally {
      global.afterEach = realAfterEach;
      global.afterAll = realAfterAll;
      jest.dontMock('./msw-server');
      jest.dontMock('./reset-shared-state');
      jest.resetModules();
    }

    return { afterEachCallbacks, afterAllCallbacks, listen, close };
  }

  it('registers exactly one afterEach, and it is the shared cleanup rather than a private copy', () => {
    const { afterEachCallbacks } = loadSetupJestWithCapturedHooks();

    expect(afterEachCallbacks).toHaveLength(1);
    expect(afterEachCallbacks[0]).toBe(runSharedAfterEach);
  });

  it('registers exactly one afterAll, and it closes the server', () => {
    const { afterAllCallbacks, close } = loadSetupJestWithCapturedHooks();

    expect(afterAllCallbacks).toHaveLength(1);
    expect(close).not.toHaveBeenCalled();

    afterAllCallbacks[0]();

    expect(close).toHaveBeenCalledTimes(1);
  });

  it('starts interception as it is evaluated, with a callback that ledgers before it raises', () => {
    const { listen } = loadSetupJestWithCapturedHooks();

    expect(listen).toHaveBeenCalledTimes(1);

    const options = listen.mock.calls[0][0] as { onUnhandledRequest: unknown };

    expect(typeof options.onUnhandledRequest).toBe('function');
  });
});

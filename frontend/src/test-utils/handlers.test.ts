/**
 * The suite that holds `./handlers`' layer-2 factories to the responses the assembled backend actually
 * produces, and holds every pattern in the module to an exact path.
 *
 * ## What this suite pins
 *
 * A handler that answers the wrong status is invisible: the service and component suites assert the outcome
 * their subject was handed, so a factory that reports `500` where the application reports `404` makes every
 * suite built on it agree with it. The oracle therefore cannot live in those suites - it has to be the
 * server-side measurement, asserted here against the same values
 * `backend/tests/integration/test_route_surface.py` and `test_http_tweets.py` assert against the real
 * application:
 *
 * | Request                                        | Status | Body                                                        |
 * |------------------------------------------------|--------|-------------------------------------------------------------|
 * | any route under `/undefined`                   | 404    | `{"detail":"Not Found"}`, `application/json`                |
 * | `GET /tweets?page=2&limit=10`, `get_db` resolved for real | 500 | `Internal Server Error`, `text/plain; charset=utf-8`  |
 * | ...with a SQLAlchemy-shaped `get_db` override  | 200    | the tweet list                                              |
 * | `GET /tweets?page=5&limit=undefined`           | 422    | one `detail` record naming `limit`                          |
 * | `GET /tweets?limit=undefined&skip=undefined`   | 422    | two records, `skip` first - declaration order, not query order |
 * | `GET /tweets/<id>`, `POST /tweets/<id>/responses` | 500 | `Internal Server Error`                                     |
 * | `POST /generate-response`, either base         | 404    | `{"detail":"Not Found"}`                                    |
 *
 * ## How the requests are issued
 *
 * `axios` directly, with `validateStatus` disabled, so a non-2xx status is read off the response rather than
 * out of an error - and so this suite asserts the **handler**, not a service's disposition of it. The service
 * suites assert the disposition. No module is mocked and no spy is installed: every request below travels the
 * real transport into msw.
 *
 * @see frontend/src/test-utils/handlers.ts - the module under test.
 * @see backend/tests/integration/test_route_surface.py - the server-side `/undefined` census.
 * @see backend/tests/integration/test_http_tweets.py - the server-side status, body and validation-order
 *   assertions.
 */

import axios from 'axios';
import type { AxiosResponse } from 'axios';

import {
  BACKEND_INTEGER_ERROR_MESSAGE,
  BACKEND_INTEGER_ERROR_TYPE,
  BACKEND_NOT_FOUND_BODY,
  BACKEND_NOT_FOUND_STATUS,
  BACKEND_SERVER_ERROR_BODY,
  BACKEND_SERVER_ERROR_STATUS,
  BACKEND_TEXT_CONTENT_TYPE,
  BACKEND_TWEETS_INT_PARAMETERS,
  BACKEND_UNPROCESSABLE_STATUS,
  CONFIGURED_BASE_PATH_PREFIX,
  CONFIGURED_BASE_URL,
  ROUTE_CONTRACTS,
  SERIALIZED_FIXED_TWEET_TIMESTAMP,
  UNSET_BASE_PATH_PREFIX,
  acknowledgeIsolationViolations,
  configuredBaseBackendHandlers,
  lastRecordedRequest,
  makeDefaultTweetsJson,
  serializeTimestamp,
  unsetBaseBackendHandlers,
} from './handlers';
import type { SerializedTweet } from './handlers';
import { fixedTweetTimestamp } from './factories';
import { server } from './msw-server';

/** Origin jsdom serves this suite from, and one of the two the handlers are registered under. */
const ORIGIN = 'http://localhost';

/** The four paths `services/api.ts` emits today, with the `/undefined` prefix its unset base URL produces. */
const UNSET_BASE_URLS = [
  `${ORIGIN}${UNSET_BASE_PATH_PREFIX}/tweets?page=2&limit=10`,
  `${ORIGIN}${UNSET_BASE_PATH_PREFIX}/tweets/42`,
  `${ORIGIN}${UNSET_BASE_PATH_PREFIX}/tweets/42/responses`,
  `${ORIGIN}${UNSET_BASE_PATH_PREFIX}/generate-response`,
] as const;

/** The same four paths once the base URL is configured: the backend's own paths. */
const CONFIGURED_TWEETS_URL = `${CONFIGURED_BASE_URL}${CONFIGURED_BASE_PATH_PREFIX}/tweets`;
const CONFIGURED_TWEET_DETAIL_URL = `${CONFIGURED_BASE_URL}${CONFIGURED_BASE_PATH_PREFIX}/tweets/42`;
const CONFIGURED_TWEET_RESPONSES_URL = `${CONFIGURED_TWEET_DETAIL_URL}/responses`;
const CONFIGURED_GENERATE_RESPONSE_URL = `${CONFIGURED_BASE_URL}${CONFIGURED_BASE_PATH_PREFIX}/generate-response`;

/** A prefix no layer names: neither the unset base nor the configured one. */
const UNNAMED_PREFIX_URL = `${ORIGIN}/api/v1/tweets?page=2&limit=10`;

/** One `detail` record of a 422 body, as the handler builds it. */
function integerError(parameter: string) {
  return { loc: ['query', parameter], msg: BACKEND_INTEGER_ERROR_MESSAGE, type: BACKEND_INTEGER_ERROR_TYPE };
}

/** Issues a request whose status is read rather than thrown, so a 4xx/5xx body stays readable. */
function request(method: 'get' | 'post', url: string): Promise<AxiosResponse<unknown>> {
  return axios.request({ method, url, validateStatus: () => true });
}

describe('every pattern names an exact path', () => {
  it('registers no wildcard segment in any route contract', () => {
    expect(ROUTE_CONTRACTS.map((contract) => contract.path)).toEqual([
      '/tweets',
      '/tweets/:tweetId',
      '/tweets/:tweetId/responses',
      '/generate-response',
    ]);
    expect(ROUTE_CONTRACTS.every((contract) => !contract.path.includes('*'))).toBe(true);
  });

  it('leaves a request under an unnamed prefix unmatched, ledgered and never performed', async () => {
    // Neither layer names `/api/v1`, so nothing answers it: msw reports it through `onUnhandledRequest`,
    // which ledgers it and raises. Silenced for this test only, then asserted on and acknowledged.
    const consoleWarn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    server.use(...unsetBaseBackendHandlers());

    try {
      await expect(request('get', UNNAMED_PREFIX_URL)).rejects.toBeDefined();

      const ledgered = acknowledgeIsolationViolations();

      expect(ledgered).toHaveLength(1);
      expect(ledgered[0]).toMatchObject({ kind: 'unhandled-request', handler: '(no handler)' });
      expect(ledgered[0].url).toContain('/api/v1/tweets');
      // Nothing answered it, so no handler recorded it either.
      expect(lastRecordedRequest()).toBeUndefined();
    } finally {
      consoleError.mockRestore();
      consoleWarn.mockRestore();
    }
  });
});

describe('the serialised timestamp is the backend’s own spelling', () => {
  /*
   * `app/schema/tweet.py` types `timestamp` as a naive `datetime` and pydantic v1 serialises it through
   * `datetime.isoformat()`, so the wire form carries no offset and no millisecond field.
   * `backend/tests/integration/test_http_tweets.py` pins the endpoint's own output as
   * `2024-01-01T00:00:00`; this is that shape, and the assertions below hold the double to it. A
   * `Date.prototype.toISOString()` value would instead read `…T12:00:00.000Z`, marking the value a
   * UTC instant — a spelling no endpoint in this application produces.
   */
  const BACKEND_TIMESTAMP_SHAPE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/;

  it('serves the fixture instant with no milliseconds and no zone marker', async () => {
    server.use(...configuredBaseBackendHandlers({ dependencyOverridden: true }));

    const response = await request('get', `${CONFIGURED_TWEETS_URL}?page=1&limit=10`);
    const served = (response.data as SerializedTweet[]).map((tweet) => tweet.timestamp);

    // The value every serialised payload carries, and the shape the backend emits.
    expect(served).toEqual([
      SERIALIZED_FIXED_TWEET_TIMESTAMP,
      SERIALIZED_FIXED_TWEET_TIMESTAMP,
      SERIALIZED_FIXED_TWEET_TIMESTAMP,
    ]);
    expect(SERIALIZED_FIXED_TWEET_TIMESTAMP).toMatch(BACKEND_TIMESTAMP_SHAPE);
    expect(SERIALIZED_FIXED_TWEET_TIMESTAMP).toBe('2024-01-15T12:00:00');
    // A spelling change only: the instant is still the one the factories build.
    expect(new Date(`${SERIALIZED_FIXED_TWEET_TIMESTAMP}Z`).getTime()).toBe(
      fixedTweetTimestamp().getTime(),
    );
    // And it is reached through the exported helper, so no caller restates the transformation.
    expect(serializeTimestamp(fixedTweetTimestamp())).toBe(SERIALIZED_FIXED_TWEET_TIMESTAMP);
  });
});

describe('unsetBaseBackendHandlers: the paths the application emits today', () => {
  it.each(UNSET_BASE_URLS.map((url) => [url] as const))('answers 404 for %s', async (url) => {
    server.use(...unsetBaseBackendHandlers());

    const response = await request(url.endsWith('/responses') || url.endsWith('-response') ? 'post' : 'get', url);

    expect(response.status).toBe(BACKEND_NOT_FOUND_STATUS);
    expect(response.data).toEqual(BACKEND_NOT_FOUND_BODY);
    expect(String(response.headers['content-type'])).toContain('application/json');
  });

  it('answers 404 whatever the query values are, because routing precedes coercion', async () => {
    server.use(...unsetBaseBackendHandlers());

    const malformed = await request(
      'get',
      `${ORIGIN}${UNSET_BASE_PATH_PREFIX}/tweets?page=5&limit=undefined`,
    );

    expect(malformed.status).toBe(BACKEND_NOT_FOUND_STATUS);
    expect(malformed.data).toEqual(BACKEND_NOT_FOUND_BODY);
  });

  it('records the request under the base the caller used', async () => {
    server.use(...unsetBaseBackendHandlers());

    await request('get', UNSET_BASE_URLS[0]);

    expect(lastRecordedRequest()).toMatchObject({
      handler: 'GET /tweets',
      base: `${ORIGIN}${UNSET_BASE_PATH_PREFIX}`,
      pathname: `${UNSET_BASE_PATH_PREFIX}/tweets`,
      status: BACKEND_NOT_FOUND_STATUS,
      violations: [],
    });
  });
});

describe('configuredBaseBackendHandlers: GET /tweets query coercion', () => {
  it('answers 422 naming limit when limit is the string "undefined"', async () => {
    server.use(...configuredBaseBackendHandlers());

    const response = await request('get', `${CONFIGURED_TWEETS_URL}?page=5&limit=undefined`);

    expect(response.status).toBe(BACKEND_UNPROCESSABLE_STATUS);
    expect(response.data).toEqual({ detail: [integerError('limit')] });
  });

  it('answers the same 422 with the database dependency overridden, because validation runs first', async () => {
    server.use(...configuredBaseBackendHandlers({ dependencyOverridden: true }));

    const response = await request('get', `${CONFIGURED_TWEETS_URL}?page=5&limit=undefined`);

    expect(response.status).toBe(BACKEND_UNPROCESSABLE_STATUS);
    expect(response.data).toEqual({ detail: [integerError('limit')] });
  });

  it('reports every failing parameter, in declaration order rather than query order', async () => {
    server.use(...configuredBaseBackendHandlers());

    // `limit` is sent first and is still reported second: the order is the order line 12 declares them in.
    const response = await request('get', `${CONFIGURED_TWEETS_URL}?limit=undefined&skip=undefined`);

    expect(response.status).toBe(BACKEND_UNPROCESSABLE_STATUS);
    expect(response.data).toEqual({ detail: [integerError('skip'), integerError('limit')] });
    expect(BACKEND_TWEETS_INT_PARAMETERS).toEqual(['skip', 'limit']);
  });

  it.each([
    ['1.5', 'fractional'],
    ['', 'empty'],
    ['abc', 'non-numeric'],
  ])('answers 422 for a %s limit (%s)', async (value) => {
    server.use(...configuredBaseBackendHandlers());

    const response = await request('get', `${CONFIGURED_TWEETS_URL}?page=1&limit=${value}`);

    expect(response.status).toBe(BACKEND_UNPROCESSABLE_STATUS);
    expect(response.data).toEqual({ detail: [integerError('limit')] });
  });

  it.each([
    ['+7', 'signed'],
    ['%208%20', 'whitespace-padded'],
    ['0', 'zero'],
  ])('accepts a %s limit (%s) and reaches the endpoint', async (value) => {
    server.use(...configuredBaseBackendHandlers({ dependencyOverridden: true }));

    const response = await request('get', `${CONFIGURED_TWEETS_URL}?page=1&limit=${value}`);

    expect(response.status).toBe(200);
    expect(response.data).toEqual(makeDefaultTweetsJson());
  });

  /*
   * pydantic v1 coerces by calling `int(value)`, so the domain is CPython's base-10 literal grammar: Unicode
   * decimal digits, scripts freely mixed, with single `_` separators strictly between digits. Each value below
   * is one the real endpoint accepts, asserted in
   * `backend/tests/integration/test_http_tweets.py::test_get_tweets_coerces_an_unconventional_integer_limit`.
   */
  it.each([
    ['1_0', 'underscore-separated'],
    ['1_0_0', 'two underscore groups'],
    ['+1_0', 'signed and underscore-separated'],
    ['\u0661\u0660', 'Arabic-Indic digits'],
    ['\uff11\uff10', 'full-width digits'],
    ['\u06f1\u06f0', 'extended Arabic-Indic digits'],
    ['\u0f21\u0f20', 'Tibetan digits'],
    ['\u0661\u0031', 'mixed-script digits'],
    ['\uff11_\uff10', 'full-width digits, underscore-separated'],
  ])('accepts %j as a limit (%s), as the endpoint does', async (value) => {
    server.use(...configuredBaseBackendHandlers({ dependencyOverridden: true }));

    const response = await request(
      'get',
      `${CONFIGURED_TWEETS_URL}?page=1&limit=${encodeURIComponent(value)}`,
    );

    expect(response.status).toBe(200);
    expect(response.data).toEqual(makeDefaultTweetsJson());
  });

  /*
   * The lookalikes `int()` refuses, asserted server-side in the same file by
   * `test_get_tweets_refuses_an_integer_lookalike`. Without these the grammar could be widened to accept an
   * underscore anywhere, or any digit-like character, and no case would fail.
   */
  it.each([
    ['_10', 'leading underscore'],
    ['10_', 'trailing underscore'],
    ['1__0', 'doubled underscore'],
    ['+_10', 'underscore after the sign'],
    ['\u2070', 'superscript zero'],
    ['\u00b2', 'superscript two'],
    ['\u00bd', 'vulgar fraction'],
  ])('answers 422 for %j as a limit (%s), as the endpoint does', async (value) => {
    server.use(...configuredBaseBackendHandlers());

    const response = await request(
      'get',
      `${CONFIGURED_TWEETS_URL}?page=1&limit=${encodeURIComponent(value)}`,
    );

    expect(response.status).toBe(BACKEND_UNPROCESSABLE_STATUS);
    expect(response.data).toEqual({ detail: [integerError('limit')] });
  });

  it('ignores page, which the backend does not declare', async () => {
    server.use(...configuredBaseBackendHandlers({ dependencyOverridden: true }));

    const response = await request('get', `${CONFIGURED_TWEETS_URL}?page=undefined&limit=10`);

    expect(response.status).toBe(200);
    expect(lastRecordedRequest()?.query).toEqual({ page: 'undefined', limit: '10' });
  });
});

describe('configuredBaseBackendHandlers: endpoint execution', () => {
  /*
   * Oracle: `backend/tests/integration/test_http_tweets.py::test_get_tweets_returns_500_without_an_override`
   * issues this request against the assembled application with `Depends(get_db)` resolved for real - only the
   * `Client` class replaced by a stand-in specified against `google.cloud.firestore.Client` - and asserts the
   * same status, the same body and the same content type. `test_get_tweets_resolves_the_declared_dependency`
   * asserts the override map was empty while it did so, and
   * `test_get_tweets_returns_500_for_the_pagination_callers_send` asserts it for the `page`/`limit` query
   * `fetchTweets` emits.
   */
  it('answers 500 with a plain-text body for GET /tweets while the dependency is not overridden', async () => {
    server.use(...configuredBaseBackendHandlers());

    const response = await request('get', `${CONFIGURED_TWEETS_URL}?page=2&limit=10`);

    expect(response.status).toBe(BACKEND_SERVER_ERROR_STATUS);
    expect(response.data).toBe(BACKEND_SERVER_ERROR_BODY);
    expect(response.headers['content-type']).toBe(BACKEND_TEXT_CONTENT_TYPE);
  });

  it('answers 200 with the tweet list once the dependency is overridden', async () => {
    server.use(...configuredBaseBackendHandlers({ dependencyOverridden: true }));

    const response = await request('get', `${CONFIGURED_TWEETS_URL}?page=2&limit=10`);

    expect(response.status).toBe(200);
    expect(response.data).toEqual(makeDefaultTweetsJson());
  });

  it.each([
    ['not overridden', false],
    ['overridden', true],
  ])('answers 500 for GET /tweets/{id} with the dependency %s', async (_label, dependencyOverridden) => {
    server.use(...configuredBaseBackendHandlers({ dependencyOverridden }));

    const response = await request('get', CONFIGURED_TWEET_DETAIL_URL);

    expect(response.status).toBe(BACKEND_SERVER_ERROR_STATUS);
    expect(response.data).toBe(BACKEND_SERVER_ERROR_BODY);
  });

  it.each([
    ['not overridden', false],
    ['overridden', true],
  ])(
    'answers 500 for POST /tweets/{id}/responses with the dependency %s',
    async (_label, dependencyOverridden) => {
      server.use(...configuredBaseBackendHandlers({ dependencyOverridden }));

      const response = await request('post', CONFIGURED_TWEET_RESPONSES_URL);

      expect(response.status).toBe(BACKEND_SERVER_ERROR_STATUS);
      expect(response.data).toBe(BACKEND_SERVER_ERROR_BODY);
    },
  );

  it('answers 404 for POST /generate-response, which no router declares under any base', async () => {
    server.use(...configuredBaseBackendHandlers());

    const response = await axios.post(
      CONFIGURED_GENERATE_RESPONSE_URL,
      { tweetId: '42' },
      { validateStatus: () => true },
    );

    expect(response.status).toBe(BACKEND_NOT_FOUND_STATUS);
    expect(response.data).toEqual(BACKEND_NOT_FOUND_BODY);
  });

  it('records the configured base rather than the unset one', async () => {
    server.use(...configuredBaseBackendHandlers());

    await request('get', `${CONFIGURED_TWEETS_URL}?page=2&limit=10`);

    expect(lastRecordedRequest()).toMatchObject({
      handler: 'GET /tweets',
      base: CONFIGURED_BASE_URL,
      pathname: '/tweets',
      status: BACKEND_SERVER_ERROR_STATUS,
    });
  });
});

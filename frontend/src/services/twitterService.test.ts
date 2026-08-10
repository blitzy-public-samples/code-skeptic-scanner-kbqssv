import axios from 'axios';
import type { AxiosResponse } from 'axios';

import * as twitterService from './twitterService';
import { getLatestTweets, getTweetDetails } from './twitterService';
import { makeFeedTweet, makeTweet } from '../test-utils/factories';
import type { FeedTweet } from '../test-utils/factories';
import {
  ALLOWED_REQUEST_ORIGINS,
  BACKEND_INTEGER_ERROR_MESSAGE,
  BACKEND_INTEGER_ERROR_TYPE,
  BACKEND_NOT_FOUND_BODY,
  BACKEND_NOT_FOUND_STATUS,
  BACKEND_SERVER_ERROR_BODY,
  BACKEND_SERVER_ERROR_STATUS,
  BACKEND_UNPROCESSABLE_STATUS,
  CONFIGURED_BASE_URL,
  SERIALIZED_FIXED_TWEET_TIMESTAMP,
  configuredBaseBackendHandlers,
  importWithConfiguredBase,
  lastRecordedRequest,
  makeDefaultTweetsJson,
  unsetBaseBackendHandlers,
} from '../test-utils/handlers';
import type { SerializedTweet } from '../test-utils/handlers';
import { server } from '../test-utils/msw-server';

const LATEST_TWEETS_COUNT = 5;

const TWEET_ID = 'abc';

const LATEST_TWEETS_URL = `undefined/tweets?page=${LATEST_TWEETS_COUNT}&limit=undefined`;

const TWEET_DETAIL_URL = `undefined/tweets/${TWEET_ID}`;

const LATEST_TWEETS_LOG_PREFIX = 'Error fetching latest tweets:';

const TWEET_DETAIL_LOG_PREFIX = 'Error fetching tweet details:';

/**
 * Origin jsdom serves this suite from, and therefore the origin every request below resolves against.
 * Asserted to be a member of `ALLOWED_REQUEST_ORIGINS` wherever it is used, so the literal stays tied to
 * the shared origin contract in `../test-utils/handlers` rather than standing on its own.
 */
const DOCUMENT_ORIGIN = 'http://localhost';

/** Paths the two subject functions resolve to once jsdom has applied the document base. */
const TWEETS_PATHNAME = '/undefined/tweets';
const TWEET_DETAIL_PATHNAME = `/undefined/tweets/${TWEET_ID}`;

/** The same two paths once `REACT_APP_API_BASE_URL` is configured: the backend's own, unprefixed paths. */
const CONFIGURED_TWEETS_PATHNAME = '/tweets';
const CONFIGURED_TWEET_DETAIL_PATHNAME = `/tweets/${TWEET_ID}`;

/** The single `detail` record fastapi returns for the `limit=undefined` this module's caller emits. */
const LIMIT_COERCION_DETAIL = {
  detail: [
    { loc: ['query', 'limit'], msg: BACKEND_INTEGER_ERROR_MESSAGE, type: BACKEND_INTEGER_ERROR_TYPE },
  ],
};

const moduleNamespace = twitterService as unknown as Record<string, unknown>;

function respondWith<T>(data: T): AxiosResponse<T> {
  return { data } as AxiosResponse<T>;
}

/** Install and restore a per-test console.error spy; restoration clears its call record. */
function silenceConsoleError() {
  return jest.spyOn(console, 'error').mockImplementation(() => undefined);
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe('getLatestTweets', () => {
  it('requests the collection with page set to its argument and limit set to the string "undefined"', async () => {
    const getSpy = jest.spyOn(axios, 'get').mockResolvedValue(respondWith<FeedTweet[]>([]));

    await getLatestTweets(LATEST_TWEETS_COUNT);

    expect(getSpy.mock.calls).toEqual([[LATEST_TWEETS_URL]]);
  });

  it('resolves to the response body without copying or reshaping it', async () => {
    const payload: FeedTweet[] = [makeFeedTweet()];
    jest.spyOn(axios, 'get').mockResolvedValue(respondWith(payload));

    await expect(getLatestTweets(LATEST_TWEETS_COUNT)).resolves.toBe(payload);
  });

  it('resolves to the tweets the default handler serves when the request runs end to end', async () => {
    await expect(getLatestTweets(LATEST_TWEETS_COUNT)).resolves.toEqual(makeDefaultTweetsJson());
  });

  it('rethrows the error it was given rather than a replacement', async () => {
    silenceConsoleError();
    const boom = new Error('boom');
    jest.spyOn(axios, 'get').mockRejectedValue(boom);

    await expect(getLatestTweets(LATEST_TWEETS_COUNT)).rejects.toBe(boom);
  });

  it('logs the failure as a prefix and the error itself before rethrowing', async () => {
    const consoleError = silenceConsoleError();
    const boom = new Error('boom');
    jest.spyOn(axios, 'get').mockRejectedValue(boom);

    await expect(getLatestTweets(LATEST_TWEETS_COUNT)).rejects.toBe(boom);

    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith(LATEST_TWEETS_LOG_PREFIX, boom);
  });

  it('rethrows the very error it logged when the request it emits today is refused as unrouted', async () => {
    const consoleError = silenceConsoleError();
    // The base URL is unset, as it is in every suite, so the emitted path is `/undefined/tweets`. No router
    // declares anything under that prefix, so starlette answers 404 before the query string is coerced -
    // which is why the malformed `limit` this caller sends never even gets looked at.
    server.use(...unsetBaseBackendHandlers());

    const caught = await getLatestTweets(LATEST_TWEETS_COUNT).catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect(caught).toMatchObject({
      response: { status: BACKEND_NOT_FOUND_STATUS, data: BACKEND_NOT_FOUND_BODY },
    });
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError.mock.calls[0][0]).toBe(LATEST_TWEETS_LOG_PREFIX);
    expect(consoleError.mock.calls[0][1]).toBe(caught);

    // The origin and path the handler answered, read back from the shared request log.
    const recorded = lastRecordedRequest();
    expect(ALLOWED_REQUEST_ORIGINS).toContain(DOCUMENT_ORIGIN);
    expect(recorded?.origin).toBe(DOCUMENT_ORIGIN);
    expect(recorded?.pathname).toBe(TWEETS_PATHNAME);
    expect(recorded?.status).toBe(BACKEND_NOT_FOUND_STATUS);
  });

  it('is refused with 422 naming limit once the base URL is configured, never reaching the endpoint', async () => {
    const consoleError = silenceConsoleError();
    server.use(...configuredBaseBackendHandlers());
    const service = await importWithConfiguredBase(() => import('./twitterService'));

    // With the request addressed at the backend's own path, the defect this module carries becomes the
    // outcome: it calls the two-parameter `fetchTweets` with one argument, so `limit` reaches the route as
    // the string `undefined`, fails `limit: int` coercion, and fastapi answers 422 before `get_tweets` runs.
    // The route-level 500 the collection would otherwise produce is therefore unreachable from this caller.
    const caught = await service.getLatestTweets(LATEST_TWEETS_COUNT).catch((error: unknown) => error);

    expect(caught).toMatchObject({
      response: { status: BACKEND_UNPROCESSABLE_STATUS, data: LIMIT_COERCION_DETAIL },
    });
    expect(consoleError.mock.calls[0][1]).toBe(caught);

    expect(lastRecordedRequest()).toMatchObject({
      base: CONFIGURED_BASE_URL,
      pathname: CONFIGURED_TWEETS_PATHNAME,
      query: { page: String(LATEST_TWEETS_COUNT), limit: 'undefined' },
      status: BACKEND_UNPROCESSABLE_STATUS,
    });
  });

  it('is refused with the same 422 when the database dependency is overridden', async () => {
    silenceConsoleError();
    server.use(...configuredBaseBackendHandlers({ dependencyOverridden: true }));
    const service = await importWithConfiguredBase(() => import('./twitterService'));

    // The override is what lets `GET /tweets` answer 200 at all, and it makes no difference here: parameter
    // coercion happens before the injected database is touched, so the disposition of `get_db` cannot turn
    // this request into a success.
    const caught = await service.getLatestTweets(LATEST_TWEETS_COUNT).catch((error: unknown) => error);

    expect(caught).toMatchObject({
      response: { status: BACKEND_UNPROCESSABLE_STATUS, data: LIMIT_COERCION_DETAIL },
    });
  });
});

describe('getTweetDetails', () => {
  it('requests the detail path with the identifier interpolated and no query string', async () => {
    const getSpy = jest
      .spyOn(axios, 'get')
      .mockResolvedValue(respondWith(makeFeedTweet({ id: TWEET_ID })));

    await getTweetDetails(TWEET_ID);

    expect(getSpy.mock.calls).toEqual([[TWEET_DETAIL_URL]]);
  });

  it('resolves to the response body without copying or reshaping it', async () => {
    const detail = makeFeedTweet({ id: TWEET_ID });
    jest.spyOn(axios, 'get').mockResolvedValue(respondWith(detail));

    await expect(getTweetDetails(TWEET_ID)).resolves.toBe(detail);
  });

  it('resolves to the tweet the default handler serves when the request runs end to end', async () => {
    const expected: SerializedTweet = {
      ...makeTweet({ tweet_id: TWEET_ID }),
      timestamp: SERIALIZED_FIXED_TWEET_TIMESTAMP,
    };

    await expect(getTweetDetails(TWEET_ID)).resolves.toEqual(expected);
  });

  it('rethrows the error it was given rather than a replacement', async () => {
    silenceConsoleError();
    const boom = new Error('boom');
    jest.spyOn(axios, 'get').mockRejectedValue(boom);

    await expect(getTweetDetails(TWEET_ID)).rejects.toBe(boom);
  });

  it('logs the failure as a prefix and the error itself before rethrowing', async () => {
    const consoleError = silenceConsoleError();
    const boom = new Error('boom');
    jest.spyOn(axios, 'get').mockRejectedValue(boom);

    await expect(getTweetDetails(TWEET_ID)).rejects.toBe(boom);

    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith(TWEET_DETAIL_LOG_PREFIX, boom);
  });

  it('rethrows the very error it logged when the request it emits today is refused as unrouted', async () => {
    const consoleError = silenceConsoleError();
    // Unrouted for the same reason as the collection case above: the `/undefined` prefix, not the id.
    server.use(...unsetBaseBackendHandlers());

    const caught = await getTweetDetails(TWEET_ID).catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect(caught).toMatchObject({
      response: { status: BACKEND_NOT_FOUND_STATUS, data: BACKEND_NOT_FOUND_BODY },
    });
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError.mock.calls[0][0]).toBe(TWEET_DETAIL_LOG_PREFIX);
    expect(consoleError.mock.calls[0][1]).toBe(caught);

    const recorded = lastRecordedRequest();
    expect(ALLOWED_REQUEST_ORIGINS).toContain(DOCUMENT_ORIGIN);
    expect(recorded?.origin).toBe(DOCUMENT_ORIGIN);
    expect(recorded?.pathname).toBe(TWEET_DETAIL_PATHNAME);
    expect(recorded?.status).toBe(BACKEND_NOT_FOUND_STATUS);
  });

  it('rethrows the 500 the route produces once the base URL is configured', async () => {
    const consoleError = silenceConsoleError();
    server.use(...configuredBaseBackendHandlers());
    const service = await importWithConfiguredBase(() => import('./twitterService'));

    // This caller sends no query string, so nothing can fail coercion and the request reaches the endpoint -
    // which reads `Tweet.id` on a model that declares no `id` and raises, for every id. So the detail route
    // is where a correctly addressed request from this module does produce the route-level 500.
    const caught = await service.getTweetDetails(TWEET_ID).catch((error: unknown) => error);

    expect(caught).toMatchObject({
      response: { status: BACKEND_SERVER_ERROR_STATUS, data: BACKEND_SERVER_ERROR_BODY },
    });
    expect(consoleError.mock.calls[0][0]).toBe(TWEET_DETAIL_LOG_PREFIX);
    expect(consoleError.mock.calls[0][1]).toBe(caught);

    expect(lastRecordedRequest()).toMatchObject({
      base: CONFIGURED_BASE_URL,
      pathname: CONFIGURED_TWEET_DETAIL_PATHNAME,
      search: '',
      status: BACKEND_SERVER_ERROR_STATUS,
      violations: [],
    });
  });
});

describe('module surface', () => {
  it('does not export getTweets, which components/TweetManagement imports and calls', () => {
    expect(Object.keys(twitterService)).not.toContain('getTweets');
    expect(moduleNamespace.getTweets).toBeUndefined();
  });

  it('exports exactly getLatestTweets and getTweetDetails, both callable', () => {
    expect([...Object.keys(twitterService)].sort()).toEqual(['getLatestTweets', 'getTweetDetails']);
    expect(typeof twitterService.getLatestTweets).toBe('function');
    expect(typeof twitterService.getTweetDetails).toBe('function');
  });
});

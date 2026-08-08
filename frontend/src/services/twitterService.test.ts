/**
 * Unit suite for `src/services/twitterService.ts`, colocated with its subject.
 *
 * The subject is a thin wrapper: each of its two functions awaits one `src/services/api.ts` function,
 * returns that value unchanged, and on failure logs to `console.error` and rethrows. This suite asserts
 * that behaviour as it stands today, including the two defects it carries.
 *
 * `api.ts` is neither imported nor mocked here - it runs for real underneath every test below, so the URL
 * it builds is part of what is asserted. Only the boundary beneath it is replaced, in two ways:
 *
 * | Mechanism                    | What it observes                                                        |
 * |------------------------------|-------------------------------------------------------------------------|
 * | `jest.spyOn(axios, 'get')`   | the URL string as `api.ts` passes it, before jsdom resolves it          |
 * | the default msw handlers     | the whole path end to end, over the real XHR adapter                    |
 *
 * jsdom resolves `undefined/tweets` against `http://localhost/`, so what reaches msw is
 * `/undefined/tweets`; the unresolved literal is observable only at the axios boundary.
 *
 * The msw lifecycle - interception, per-test handler reset and shutdown - belongs to
 * `src/test-utils/setup-jest.ts` and is not re-registered here. That module also deletes
 * `REACT_APP_API_BASE_URL`, which is why `api.ts` prefixes every request with the string `undefined`.
 *
 * @see frontend/src/services/twitterService.ts - the module under test.
 * @see frontend/TESTING.md - the msw contract and the `server.use(...)` idiom.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this suite is shaped this way.
 * @see docs/testing/TRACEABILITY-MATRIX.md - the mapping back to the covered constructs.
 */

import axios from 'axios';
import type { AxiosResponse } from 'axios';
import { rest } from 'msw';

import * as twitterService from './twitterService';
import { getLatestTweets, getTweetDetails } from './twitterService';
import { FIXED_TWEET_TIMESTAMP, makeFeedTweet, makeTweet } from '../test-utils/factories';
import type { FeedTweet } from '../test-utils/factories';
import { makeDefaultTweetsJson } from '../test-utils/handlers';
import type { SerializedTweet } from '../test-utils/handlers';
import { server } from '../test-utils/msw-server';

/** Argument passed to `getLatestTweets`, which reaches the URL as the `page` query value. */
const LATEST_TWEETS_COUNT = 5;

/** Identifier passed to `getTweetDetails`, which reaches the URL as the final path segment. */
const TWEET_ID = 'abc';

/**
 * URL `getLatestTweets(5)` hands to axios.
 *
 * `limit` is the string `undefined` because line 12 of the subject calls the two-parameter
 * `fetchTweets(page, limit)` with one argument, and the base is the string `undefined` because line 5 of
 * `api.ts` interpolates an unset environment variable. Both are template-literal interpolations of
 * `undefined`, not absent values.
 */
const LATEST_TWEETS_URL = `undefined/tweets?page=${LATEST_TWEETS_COUNT}&limit=undefined`;

/** URL `getTweetDetails('abc')` hands to axios. The subject sends no query string on this route. */
const TWEET_DETAIL_URL = `undefined/tweets/${TWEET_ID}`;

/** First argument of the `console.error` call on line 15 of the subject. */
const LATEST_TWEETS_LOG_PREFIX = 'Error fetching latest tweets:';

/** First argument of the `console.error` call on line 25 of the subject. */
const TWEET_DETAIL_LOG_PREFIX = 'Error fetching tweet details:';

/** Patterns `src/test-utils/handlers.ts` already registers, overridden per test rather than added to. */
const TWEETS_ROUTE_PATTERN = '*/tweets';
const TWEET_DETAIL_ROUTE_PATTERN = '*/tweets/:tweetId';

/** Status the overridden handlers answer with so the real axios adapter rejects. */
const SERVER_ERROR_STATUS = 500;

/** The module namespace as a plain record, so a member it does not declare can be read back. */
const moduleNamespace = twitterService as unknown as Record<string, unknown>;

/**
 * A stand-in for the `AxiosResponse` the subject's dependency reads. `api.ts` touches `data` and nothing
 * else, so `data` is all this carries, and it is returned by identity all the way out of the subject.
 *
 * @param data - Value to expose as the response body.
 */
function respondWith<T>(data: T): AxiosResponse<T> {
  return { data } as AxiosResponse<T>;
}

/**
 * Replaces `console.error` for the duration of one test. `setup-jest.ts` deliberately leaves the console
 * alone, so each test that drives the subject's failure path installs this itself.
 *
 * Call sites read `mock.calls` before the suite's `afterEach` restores the spy: `mockRestore()` also resets
 * the spy, which discards the recorded calls.
 */
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

    // One call, one argument: `api.ts` passes the URL alone and no request config.
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

  it('rethrows the very error it logged when the failure comes from the real adapter', async () => {
    const consoleError = silenceConsoleError();
    server.use(
      rest.get(TWEETS_ROUTE_PATTERN, (_req, res, ctx) => res(ctx.status(SERVER_ERROR_STATUS))),
    );

    const caught = await getLatestTweets(LATEST_TWEETS_COUNT).catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError.mock.calls[0][0]).toBe(LATEST_TWEETS_LOG_PREFIX);
    // The logged error and the escaping error are one object, which no wrapping rethrow could produce.
    expect(consoleError.mock.calls[0][1]).toBe(caught);
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
    // The handler echoes the path parameter into `tweet_id`, and JSON serialisation turns the fixture's
    // real `Date` into an ISO-8601 string.
    const expected: SerializedTweet = {
      ...makeTweet({ tweet_id: TWEET_ID }),
      timestamp: FIXED_TWEET_TIMESTAMP,
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

  it('rethrows the very error it logged when the failure comes from the real adapter', async () => {
    const consoleError = silenceConsoleError();
    server.use(
      rest.get(TWEET_DETAIL_ROUTE_PATTERN, (_req, res, ctx) => res(ctx.status(SERVER_ERROR_STATUS))),
    );

    const caught = await getTweetDetails(TWEET_ID).catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError.mock.calls[0][0]).toBe(TWEET_DETAIL_LOG_PREFIX);
    expect(consoleError.mock.calls[0][1]).toBe(caught);
  });
});

describe('module surface', () => {
  it('does not export getTweets, which components/TweetManagement imports and calls', () => {
    // That import resolves to `undefined` and the call raises a TypeError the component logs; the
    // component suite asserts that log, and this assertion is the other half of the same fact.
    expect(Object.keys(twitterService)).not.toContain('getTweets');
    expect(moduleNamespace.getTweets).toBeUndefined();
  });

  it('exports exactly getLatestTweets and getTweetDetails, both callable', () => {
    // `__esModule` is defined with `Object.defineProperty` and so is not enumerable; the `Tweet`
    // interface is a type and is erased. Neither appears here.
    expect([...Object.keys(twitterService)].sort()).toEqual(['getLatestTweets', 'getTweetDetails']);
    expect(typeof twitterService.getLatestTweets).toBe('function');
    expect(typeof twitterService.getTweetDetails).toBe('function');
  });
});

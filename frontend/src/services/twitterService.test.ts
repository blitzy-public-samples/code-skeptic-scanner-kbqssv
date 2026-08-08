import axios from 'axios';
import type { AxiosResponse } from 'axios';

import * as twitterService from './twitterService';
import { getLatestTweets, getTweetDetails } from './twitterService';
import { FIXED_TWEET_TIMESTAMP, makeFeedTweet, makeTweet } from '../test-utils/factories';
import type { FeedTweet } from '../test-utils/factories';
import {
  ALLOWED_REQUEST_ORIGINS,
  currentBehaviorTweetByIdHandlers,
  currentBehaviorTweetsHandlers,
  lastRecordedRequest,
  makeDefaultTweetsJson,
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

/** Status the shared current-behaviour handlers answer with, so the real axios adapter rejects. */
const SERVER_ERROR_STATUS = 500;

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

  it('rethrows the very error it logged when the failure comes from the real adapter', async () => {
    const consoleError = silenceConsoleError();
    // The shared origin-scoped factory rather than a wildcard-prefixed pattern of this suite's own: it
    // registers one handler per entry in `ALLOWED_REQUEST_ORIGINS`, so a request addressed anywhere
    // else matches nothing, reaches `onUnhandledRequest` and fails the test through the isolation
    // ledger rather than being answered regardless of its origin.
    server.use(...currentBehaviorTweetsHandlers());

    const caught = await getLatestTweets(LATEST_TWEETS_COUNT).catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError.mock.calls[0][0]).toBe(LATEST_TWEETS_LOG_PREFIX);
    expect(consoleError.mock.calls[0][1]).toBe(caught);

    // The origin and path the handler answered, read back from the shared request log.
    const recorded = lastRecordedRequest();
    expect(ALLOWED_REQUEST_ORIGINS).toContain(DOCUMENT_ORIGIN);
    expect(recorded?.origin).toBe(DOCUMENT_ORIGIN);
    expect(recorded?.pathname).toBe(TWEETS_PATHNAME);
    expect(recorded?.status).toBe(SERVER_ERROR_STATUS);
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
    // Origin-scoped for the same reason as the collection case above.
    server.use(...currentBehaviorTweetByIdHandlers());

    const caught = await getTweetDetails(TWEET_ID).catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError.mock.calls[0][0]).toBe(TWEET_DETAIL_LOG_PREFIX);
    expect(consoleError.mock.calls[0][1]).toBe(caught);

    const recorded = lastRecordedRequest();
    expect(ALLOWED_REQUEST_ORIGINS).toContain(DOCUMENT_ORIGIN);
    expect(recorded?.origin).toBe(DOCUMENT_ORIGIN);
    expect(recorded?.pathname).toBe(TWEET_DETAIL_PATHNAME);
    expect(recorded?.status).toBe(SERVER_ERROR_STATUS);
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

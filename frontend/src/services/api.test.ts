
import axios from 'axios';

import {
  ALLOWED_REQUEST_ORIGINS,
  DEFAULT_GENERATED_RESPONSE,
  currentBehaviorTweetByIdHandlers,
  lastRecordedRequest,
  makeDefaultTweetsJson,
} from '../test-utils/handlers';
import { server } from '../test-utils/msw-server';
import { FIXED_TWEET_TIMESTAMP, makeTweet } from '../test-utils/factories';

import { fetchTweetById, fetchTweets, generateResponse } from './api';
import * as apiModule from './api';

/**
 * Origin jsdom serves this suite from, and therefore the origin every request below resolves against.
 * Asserted to be a member of `ALLOWED_REQUEST_ORIGINS` wherever it is used, so the literal stays tied to
 * the shared origin contract in `../test-utils/handlers` rather than standing on its own.
 */
const DOCUMENT_ORIGIN = 'http://localhost';

/** Path `fetchTweetById('42')` resolves to once jsdom has applied the document base. */
const TWEET_DETAIL_PATHNAME = '/undefined/tweets/42';

/** Status the shared current-behaviour tweet-detail handlers answer with. */
const SERVER_ERROR_STATUS = 500;

/** Restore axios spies; clearMocks resets calls but does not remove spy implementations. */
afterEach(() => {
  jest.restoreAllMocks();
});

describe('fetchTweets', () => {
  it('requests the literal "undefined" base URL with page and limit in the query string', async () => {
    const get = jest.spyOn(axios, 'get').mockResolvedValue({ data: [] });

    await fetchTweets(2, 10);

    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith('undefined/tweets?page=2&limit=10');
    expect(get.mock.calls[0]).toEqual(['undefined/tweets?page=2&limit=10']);
  });

  it('resolves with the response body itself, neither copied nor transformed', async () => {
    const body = makeDefaultTweetsJson();
    jest.spyOn(axios, 'get').mockResolvedValue({ data: body });

    const result = await fetchTweets(1, 10);

    expect(result).toBe(body);
  });

  it('resolves with the intercepted tweet collection when the request crosses the HTTP boundary', async () => {
    const result = await fetchTweets(1, 20);

    expect(result).toEqual(makeDefaultTweetsJson());
    expect(result).toHaveLength(3);
  });

  it('emits a contract-conforming request whose path carries the "undefined" base segment', async () => {
    await fetchTweets(3, 25);

    const recorded = lastRecordedRequest();
    expect(recorded).toBeDefined();
    expect(recorded?.method).toBe('GET');
    expect(recorded?.pathname).toBe('/undefined/tweets');
    expect(recorded?.search).toBe('?page=3&limit=25');
    expect(recorded?.query).toEqual({ page: '3', limit: '25' });
    expect(recorded?.status).toBe(200);
    expect(recorded?.violations).toEqual([]);
  });

  it('propagates the rejection instance unchanged', async () => {
    const boom = new Error('boom');
    jest.spyOn(axios, 'get').mockRejectedValue(boom);

    await expect(fetchTweets(1, 10)).rejects.toBe(boom);
  });
});

describe('fetchTweetById', () => {
  it('requests the literal "undefined" base URL with the tweet id as the last path segment', async () => {
    const get = jest.spyOn(axios, 'get').mockResolvedValue({ data: makeTweet() });

    await fetchTweetById('42');

    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith('undefined/tweets/42');
    expect(get.mock.calls[0]).toEqual(['undefined/tweets/42']);
  });

  it('interpolates the tweet id into the URL string verbatim, without encoding or trimming it', async () => {
    const get = jest.spyOn(axios, 'get').mockResolvedValue({ data: makeTweet() });

    await fetchTweetById('tweet 1/../7');

    // The string `api.ts` built, observed before any adapter parses it. `axios` is mocked here, so no
    // URL parser runs and the traversal segment is still present as written. What the network receives
    // is a different string; the case below asserts that one.
    expect(get).toHaveBeenCalledWith('undefined/tweets/tweet 1/../7');
  });

  it('lets a traversal segment in the tweet id retarget the request at the network boundary', async () => {
    // No axios spy: the request travels over the real adapter, so jsdom resolves it against the document
    // base and the URL parser applies path normalisation before msw matches a handler.
    const result = await fetchTweetById('tweet 1/../7');

    const recorded = lastRecordedRequest();
    expect(recorded).toBeDefined();
    expect(recorded?.method).toBe('GET');
    // `..` removes the preceding `tweet%201` segment, so the id `api.ts` sent is gone from the path.
    expect(recorded?.url).toBe('http://localhost/undefined/tweets/7');
    expect(recorded?.pathname).toBe('/undefined/tweets/7');
    expect(recorded?.pathname).not.toContain('..');
    // The id itself is absent in both spellings: as written, and percent-encoded as jsdom would send it.
    expect(recorded?.pathname).not.toContain('tweet 1');
    expect(recorded?.pathname).not.toContain('tweet%201');
    // The route parameter the backend would bind is `7`, not the identifier the caller asked for.
    expect(recorded?.pathParams).toEqual({ tweetId: '7' });
    expect(recorded?.status).toBe(200);
    expect(recorded?.violations).toEqual([]);
    // And the caller is handed the record for the retargeted id, with nothing signalling the switch:
    // `api.ts` neither validates nor encodes the id, and no error is raised on either side.
    expect(result.tweet_id).toBe('7');
  });

  it('resolves with the response body itself, neither copied nor transformed', async () => {
    const body = makeTweet({ tweet_id: '42' });
    jest.spyOn(axios, 'get').mockResolvedValue({ data: body });

    const result = await fetchTweetById('42');

    expect(result).toBe(body);
    expect(result.timestamp).toBeInstanceOf(Date);
  });

  it('resolves with the intercepted tweet, whose timestamp arrives as an ISO string', async () => {
    const result = await fetchTweetById('42');

    expect(result).toEqual({ ...makeTweet({ tweet_id: '42' }), timestamp: FIXED_TWEET_TIMESTAMP });
    expect(typeof result.timestamp).toBe('string');
  });

  it('propagates the rejection instance unchanged', async () => {
    const boom = new Error('boom');
    jest.spyOn(axios, 'get').mockRejectedValue(boom);

    await expect(fetchTweetById('42')).rejects.toBe(boom);
  });

  it('rejects with the axios error carrying the response when the route answers 500', async () => {
    // The shared origin-scoped factory rather than a wildcard-prefixed pattern of this suite's own:
    // it registers one handler per entry in `ALLOWED_REQUEST_ORIGINS`, so a request emitted to any
    // other origin matches nothing, reaches `onUnhandledRequest` and fails the test through the
    // isolation ledger instead of being answered regardless of where it was addressed.
    server.use(...currentBehaviorTweetByIdHandlers());

    const caught = await fetchTweetById('42').catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect(caught).toMatchObject({
      message: `Request failed with status code ${SERVER_ERROR_STATUS}`,
      response: { status: SERVER_ERROR_STATUS },
    });

    /* The origin and path the handler actually answered, read back from the shared request log. */
    const recorded = lastRecordedRequest();
    expect(ALLOWED_REQUEST_ORIGINS).toContain(DOCUMENT_ORIGIN);
    expect(recorded?.origin).toBe(DOCUMENT_ORIGIN);
    expect(recorded?.pathname).toBe(TWEET_DETAIL_PATHNAME);
    expect(recorded?.status).toBe(SERVER_ERROR_STATUS);
    expect(recorded?.violations).toEqual([]);
  });
});

describe('generateResponse', () => {
  it('posts the tweet id as a JSON body to the literal "undefined" base URL', async () => {
    const post = jest
      .spyOn(axios, 'post')
      .mockResolvedValue({ data: { generatedResponse: DEFAULT_GENERATED_RESPONSE } });

    await generateResponse('42');

    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith('undefined/generate-response', { tweetId: '42' });
    expect(post.mock.calls[0]).toEqual(['undefined/generate-response', { tweetId: '42' }]);
  });

  it('resolves with the generatedResponse field alone, not the enclosing body', async () => {
    const body = { generatedResponse: 'x', other: 'y' };
    jest.spyOn(axios, 'post').mockResolvedValue({ data: body });

    const result = await generateResponse('42');

    expect(result).toBe('x');
    expect(result).not.toEqual(body);
  });

  it('resolves undefined when the response body carries no generatedResponse field', async () => {
    jest.spyOn(axios, 'post').mockResolvedValue({ data: {} });

    await expect(generateResponse('42')).resolves.toBeUndefined();
  });

  it('resolves with the intercepted generated response when the request crosses the HTTP boundary', async () => {
    const result = await generateResponse('42');

    expect(result).toBe(DEFAULT_GENERATED_RESPONSE);
  });

  it('emits a contract-conforming JSON request carrying only the tweet id', async () => {
    await generateResponse('tweet-1');

    const recorded = lastRecordedRequest();
    expect(recorded).toBeDefined();
    expect(recorded?.method).toBe('POST');
    expect(recorded?.pathname).toBe('/undefined/generate-response');
    expect(recorded?.search).toBe('');
    expect(recorded?.contentType).toBe('application/json');
    expect(recorded?.body).toEqual({ tweetId: 'tweet-1' });
    expect(recorded?.status).toBe(200);
    expect(recorded?.violations).toEqual([]);
  });

  it('propagates the rejection instance unchanged', async () => {
    const boom = new Error('boom');
    jest.spyOn(axios, 'post').mockRejectedValue(boom);

    await expect(generateResponse('42')).rejects.toBe(boom);
  });
});

describe('module surface', () => {
  it('exports exactly the three request functions', () => {
    expect(Object.keys(apiModule).sort()).toEqual([
      'fetchTweetById',
      'fetchTweets',
      'generateResponse',
    ]);
    expect(typeof apiModule.fetchTweets).toBe('function');
    expect(typeof apiModule.fetchTweetById).toBe('function');
    expect(typeof apiModule.generateResponse).toBe('function');
  });

  it('exports no axios instance under the name api', () => {
    expect(Object.keys(apiModule)).not.toContain('api');
    expect(apiModule).not.toHaveProperty('api');
  });

  it('exports no setupInterceptors function', () => {
    expect(Object.keys(apiModule)).not.toContain('setupInterceptors');
    expect(apiModule).not.toHaveProperty('setupInterceptors');
  });
});

/**
 * Unit suite for `src/services/api.ts`, the axios wrapper `services/twitterService.ts` and
 * `services/llmService.ts` both import through the bare specifier `app/services/api`.
 *
 * ## The base URL is the literal string `undefined`
 *
 * `api.ts` reads `process.env.REACT_APP_API_BASE_URL` once, at module scope, into the base URL it
 * prefixes every request with. `src/test-utils/setup-jest.ts` removes that variable before any module in
 * the graph can read it, so the base is `undefined` and template interpolation makes it the literal
 * four-character string `undefined`. Every URL asserted below therefore begins `undefined/`; that string
 * is the oracle, not a stand-in for one.
 *
 * ## The module neither catches nor transforms
 *
 * There is no `try`/`catch` and no conditional anywhere in `api.ts`. Each rejection reaches the caller as
 * the instance axios raised, and each resolved value is `response.data` - for `generateResponse`,
 * `response.data.generatedResponse` - with nothing copied, validated or defaulted.
 *
 * ## Two observation points
 *
 * An `axios` method spy records the URL string `api.ts` constructed, as its own argument.
 *
 * The default handlers in `src/test-utils/handlers.ts` record the request where it reaches the network
 * boundary, over the real axios adapter and after jsdom has resolved it against the document base - so a
 * handler sees `http://localhost/undefined/tweets`, which is a different string from the argument. Their
 * wildcard-prefixed patterns cover `/tweets`, `/tweets/:tweetId` and `/generate-response`, every URL this
 * module issues. This suite adds no default pattern, and each `server.use(...)` override stays inside
 * the one test that needs it.
 *
 * Every spy below is given a mocked return value in the statement that creates it. An `axios` spy
 * without one calls through and opens a socket.
 *
 * @see frontend/TESTING.md - the msw contract and the `server.use(...)` idiom.
 * @see docs/testing/DECISION-LOG.md - the rationale for every choice made in this file.
 * @see docs/testing/TRACEABILITY-MATRIX.md - this suite mapped back to the three exported functions.
 */

import axios from 'axios';
import { rest } from 'msw';

import {
  DEFAULT_GENERATED_RESPONSE,
  lastRecordedRequest,
  makeDefaultTweetsJson,
} from '../test-utils/handlers';
import { server } from '../test-utils/msw-server';
import { FIXED_TWEET_TIMESTAMP, makeTweet } from '../test-utils/factories';

import { fetchTweetById, fetchTweets, generateResponse } from './api';
import * as apiModule from './api';

/**
 * Removes every `axios` spy, leaving the next test to install its own or to reach the msw boundary
 * through the real adapter. `clearMocks` in `jest.config.js` clears call bookkeeping between tests but
 * leaves mock implementations installed; this hook is what removes them.
 */
afterEach(() => {
  jest.restoreAllMocks();
});

describe('fetchTweets', () => {
  it('requests the literal "undefined" base URL with page and limit in the query string', async () => {
    const get = jest.spyOn(axios, 'get').mockResolvedValue({ data: [] });

    await fetchTweets(2, 10);

    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith('undefined/tweets?page=2&limit=10');
    // `api.ts` passes the URL alone, with no axios request config.
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

  it('sends the tweet id verbatim, without encoding or trimming it', async () => {
    const get = jest.spyOn(axios, 'get').mockResolvedValue({ data: makeTweet() });

    await fetchTweetById('tweet 1/../7');

    expect(get).toHaveBeenCalledWith('undefined/tweets/tweet 1/../7');
  });

  it('resolves with the response body itself, neither copied nor transformed', async () => {
    const body = makeTweet({ tweet_id: '42' });
    jest.spyOn(axios, 'get').mockResolvedValue({ data: body });

    const result = await fetchTweetById('42');

    expect(result).toBe(body);
    // Nothing serialises on this path, so the `Date` the factory built arrives as a `Date`.
    expect(result.timestamp).toBeInstanceOf(Date);
  });

  it('resolves with the intercepted tweet, whose timestamp arrives as an ISO string', async () => {
    const result = await fetchTweetById('42');

    expect(result).toEqual({ ...makeTweet({ tweet_id: '42' }), timestamp: FIXED_TWEET_TIMESTAMP });
    // JSON carries no Date, so the field the schema types as `z.date()` crosses the wire as a string.
    expect(typeof result.timestamp).toBe('string');
  });

  it('propagates the rejection instance unchanged', async () => {
    const boom = new Error('boom');
    jest.spyOn(axios, 'get').mockRejectedValue(boom);

    await expect(fetchTweetById('42')).rejects.toBe(boom);
  });

  it('rejects with the axios error carrying the response when the route answers 500', async () => {
    server.use(rest.get('*/tweets/:tweetId', (_req, res, ctx) => res(ctx.status(500))));

    const caught = await fetchTweetById('42').catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect(caught).toMatchObject({
      message: 'Request failed with status code 500',
      response: { status: 500 },
    });
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
    // The URL and the body, and no third axios request-config argument.
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

/**
 * The module's export list, asserted in both directions.
 *
 * Two symbols other modules import from here are absent. `store/tweetSlice.ts` imports `api` and calls
 * `api.get('/tweets')` inside a `try`/`catch`, so that thunk rejects with `'Failed to fetch tweets'`;
 * `app.tsx` and `index.tsx` import `setupInterceptors` and invoke it. Both absences are the module's
 * current surface, and both are pinned below.
 */
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

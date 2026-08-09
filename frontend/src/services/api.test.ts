
import axios from 'axios';

import {
  ALLOWED_REQUEST_ORIGINS,
  BACKEND_NOT_FOUND_BODY,
  BACKEND_NOT_FOUND_STATUS,
  BACKEND_SERVER_ERROR_BODY,
  BACKEND_SERVER_ERROR_STATUS,
  CONFIGURED_BASE_URL,
  DEFAULT_GENERATED_RESPONSE,
  configuredBaseBackendHandlers,
  importWithConfiguredBase,
  lastRecordedRequest,
  makeDefaultTweetsJson,
  unsetBaseBackendHandlers,
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

/**
 * The same call's path once `REACT_APP_API_BASE_URL` is `CONFIGURED_BASE_URL`: the backend's own route path,
 * with no prefix. The unprefixed form is not a stylistic choice - `app/main.py` includes its router at the
 * root, so this is the only shape the backend routes.
 */
const CONFIGURED_TWEET_DETAIL_PATHNAME = '/tweets/42';

/** Path the collection request lands on under the same configured base. */
const CONFIGURED_TWEETS_PATHNAME = '/tweets';

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

  it('resolves with the frontend-isolation fixture when the request crosses the HTTP boundary', async () => {
    // The 200 below is `../test-utils/handlers`' isolation fixture, not an outcome the backend produces:
    // this exact request is answered 404 by the assembled application, which the two cases at the end of
    // this file assert. What is being asserted here is that the resolved value reaches the caller
    // untransformed.
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

  it('rejects with a 404 for the path it emits today, because that path is not routed', async () => {
    server.use(...unsetBaseBackendHandlers());

    const caught = await fetchTweets(2, 10).catch((error: unknown) => error);

    expect(caught).toMatchObject({
      response: { status: BACKEND_NOT_FOUND_STATUS, data: BACKEND_NOT_FOUND_BODY },
    });
    expect(lastRecordedRequest()).toMatchObject({
      pathname: '/undefined/tweets',
      status: BACKEND_NOT_FOUND_STATUS,
    });
  });

  it('rejects with a 500 once the base URL is configured and both query values coerce to int', async () => {
    server.use(...configuredBaseBackendHandlers());
    const api = await importWithConfiguredBase(() => import('./api'));

    // `fetchTweets` is the only caller that sends a usable `limit`, so it is the only one whose request gets
    // past query coercion and reaches the endpoint body - where `db.query` on the Firestore client raises.
    // `page` is not a declared parameter and is ignored, so it does not affect the outcome.
    const caught = await api.fetchTweets(2, 10).catch((error: unknown) => error);

    expect(caught).toMatchObject({
      response: { status: BACKEND_SERVER_ERROR_STATUS, data: BACKEND_SERVER_ERROR_BODY },
    });
    expect(lastRecordedRequest()).toMatchObject({
      base: CONFIGURED_BASE_URL,
      pathname: CONFIGURED_TWEETS_PATHNAME,
      query: { page: '2', limit: '10' },
      status: BACKEND_SERVER_ERROR_STATUS,
      violations: [],
    });
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
    // The last path segment carries `7`, so a route pattern of this shape binds `7` rather than the
    // identifier the caller asked for. This is msw's binding of the emitted path; the case below drives the
    // same call at the backend's own path, which is where that binding would be the route's.
    expect(recorded?.pathParams).toEqual({ tweetId: '7' });
    // The 200 and the returned record are the isolation fixture's, not the backend's: this path carries the
    // unrouted `/undefined` prefix, so the application answers 404 for it. What production supplies here is
    // the retargeting - nothing on either side signals it, because `api.ts` neither validates nor encodes
    // the id.
    expect(recorded?.status).toBe(200);
    expect(recorded?.violations).toEqual([]);
    expect(result.tweet_id).toBe('7');
  });

  it('lands the retargeted request on the backend route once the base URL is configured', async () => {
    server.use(...configuredBaseBackendHandlers());
    const api = await importWithConfiguredBase(() => import('./api'));

    // The same traversal, now against a base URL the backend routes. The request reaches
    // `GET /tweets/{tweet_id}` with `7` as the path parameter, and that route answers 500 for every id, so
    // the retargeting is not hypothetical: it selects a real route and a real record.
    const caught = await api.fetchTweetById('tweet 1/../7').catch((error: unknown) => error);

    expect(caught).toMatchObject({ response: { status: BACKEND_SERVER_ERROR_STATUS } });
    expect(lastRecordedRequest()).toMatchObject({
      base: CONFIGURED_BASE_URL,
      pathname: '/tweets/7',
      pathParams: { tweetId: '7' },
      status: BACKEND_SERVER_ERROR_STATUS,
      violations: [],
    });
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

  it('rejects with a 404 for the path it emits today, because that path is not routed', async () => {
    // The base URL is unset here, as it is in every suite, so the emitted path carries the `/undefined`
    // segment. `app/main.py` declares `/tweets/{tweet_id}` and nothing under `/undefined`, so starlette's
    // router refuses the request before any dependency resolves - this 404 is the router, not the handler's
    // "Tweet not found" branch, which is unreachable.
    server.use(...unsetBaseBackendHandlers());

    const caught = await fetchTweetById('42').catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect(caught).toMatchObject({
      message: `Request failed with status code ${BACKEND_NOT_FOUND_STATUS}`,
      response: { status: BACKEND_NOT_FOUND_STATUS, data: BACKEND_NOT_FOUND_BODY },
    });

    /* The origin and path the handler actually answered, read back from the shared request log. */
    const recorded = lastRecordedRequest();
    expect(ALLOWED_REQUEST_ORIGINS).toContain(DOCUMENT_ORIGIN);
    expect(recorded?.origin).toBe(DOCUMENT_ORIGIN);
    expect(recorded?.pathname).toBe(TWEET_DETAIL_PATHNAME);
    expect(recorded?.status).toBe(BACKEND_NOT_FOUND_STATUS);
    expect(recorded?.violations).toEqual([]);
  });

  it('rejects with a 500 once the base URL is configured and the request reaches the route', async () => {
    server.use(...configuredBaseBackendHandlers());
    const api = await importWithConfiguredBase(() => import('./api'));

    const caught = await api.fetchTweetById('42').catch((error: unknown) => error);

    // The route reads `Tweet.id` on a pydantic model that declares no `id`, so it raises for every id and
    // starlette answers with its plain-text 500 body rather than JSON.
    expect(caught).toBeInstanceOf(Error);
    expect(caught).toMatchObject({
      message: `Request failed with status code ${BACKEND_SERVER_ERROR_STATUS}`,
      response: { status: BACKEND_SERVER_ERROR_STATUS, data: BACKEND_SERVER_ERROR_BODY },
    });

    expect(lastRecordedRequest()).toMatchObject({
      base: CONFIGURED_BASE_URL,
      pathname: CONFIGURED_TWEET_DETAIL_PATHNAME,
      status: BACKEND_SERVER_ERROR_STATUS,
      violations: [],
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

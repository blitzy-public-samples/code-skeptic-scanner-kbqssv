/**
 * The suite for `./llmService`, whose single export `generateTweetResponse(tweetId)` wraps
 * `services/api.ts` `generateResponse` in a `try`/`catch`.
 *
 * Two dispositions, and they are asymmetric:
 *
 * | Outcome of `generateResponse` | What `generateTweetResponse` does                                        |
 * |-------------------------------|--------------------------------------------------------------------------|
 * | resolves                      | returns the value verbatim - no inspection, no transformation, no default |
 * | rejects                       | logs the original error, then throws a **new** `Error` in its place       |
 *
 * On the rejected path the original error reaches `console.error` but never reaches the caller. The
 * caller is handed a fresh `Error` whose message is exactly {@link REPLACEMENT_ERROR_MESSAGE} and
 * which carries nothing else - not the status, not the request, not the AxiosError shape. The thrown
 * value is therefore never the value that caused it, and the value that caused it appears only in the
 * log.
 *
 * `services/twitterService.ts` re-throws the original instance from the same shape of `catch`. The
 * two sibling services therefore dispose of a failure differently; the test names say so.
 *
 * Nothing here mocks the subject or the module beneath it. `app/services/api` resolves to the real
 * `services/api.ts` through the `moduleNameMapper` entry in `frontend/jest.config.js`, so that module
 * executes on every path below. Only the boundary under it is replaced: msw intercepts the request
 * for the tests that exercise the transport, and a spy on `axios.post` stands in for the tests that
 * need a specific settled outcome without one.
 *
 * @see frontend/src/services/llmService.ts - the module under test.
 * @see frontend/src/services/api.ts - `generateResponse`, which runs beneath it.
 * @see frontend/src/test-utils/handlers.ts - the `generate-response` handler and the request log.
 * @see frontend/TESTING.md - the msw contract and the `server.use(...)` idiom.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why these oracles, and the
 *   mocking boundary they are asserted across, are what they are.
 */

import axios from 'axios';

import { generateTweetResponse } from './llmService';
import {
  BACKEND_NOT_FOUND_STATUS,
  DEFAULT_GENERATED_RESPONSE,
  currentBehaviorGenerateResponseHandlers,
  lastRecordedRequest,
  recordedRequests,
} from '../test-utils/handlers';
import { server } from '../test-utils/msw-server';

/** Tweet id the subject is called with. Non-empty, so it satisfies the route's body contract. */
const SUBJECT_TWEET_ID = 'tweet-1';

/** Message of the error the subject throws in place of whatever it caught. */
const REPLACEMENT_ERROR_MESSAGE = 'Failed to generate tweet response';

/** First argument of the subject's `console.error` call, sent with the original error as the second. */
const LOG_PREFIX = 'Error generating tweet response:';

/** Absolute path the request reaches, with `services/api.ts`'s unset base URL as the first segment. */
const REQUEST_PATHNAME = '/undefined/generate-response';

/** A response distinct from the canned one, for asserting the value is passed through unchanged. */
const SPIED_GENERATED_RESPONSE = 'hello';

/**
 * Removes the `axios.post` and `console.error` spies the tests below install, restoring both to the
 * originals.
 *
 * `frontend/jest.config.js` sets `clearMocks`, which resets call bookkeeping between tests and leaves
 * mock implementations in place; a settled outcome installed by one test is discarded here.
 */
afterEach(() => {
  jest.restoreAllMocks();
});

describe('generateTweetResponse: resolved disposition', () => {
  it('resolves with the generated response the API layer unwrapped, over the real transport', async () => {
    const result = await generateTweetResponse(SUBJECT_TWEET_ID);

    expect(result).toBe(DEFAULT_GENERATED_RESPONSE);

    // Nothing is mocked on this path, so the value came through msw, axios and the real
    // `services/api.ts` unwrap of `response.data.generatedResponse`.
    expect(recordedRequests()).toHaveLength(1);
  });

  it('returns the value the API layer produced verbatim, without inspecting or transforming it', async () => {
    // The spy carries its settled outcome; `jest.spyOn` on its own calls through to real axios.
    const post = jest
      .spyOn(axios, 'post')
      .mockResolvedValue({ data: { generatedResponse: SPIED_GENERATED_RESPONSE } });

    const result = await generateTweetResponse(SUBJECT_TWEET_ID);

    expect(result).toBe(SPIED_GENERATED_RESPONSE);
    expect(post).toHaveBeenCalledTimes(1);

    // The spy answered, so no request was issued and no handler ran.
    expect(recordedRequests()).toEqual([]);
  });

  it('forwards its tweetId argument into the request body unchanged', async () => {
    await generateTweetResponse(SUBJECT_TWEET_ID);

    expect(lastRecordedRequest()).toMatchObject({
      method: 'POST',
      pathname: REQUEST_PATHNAME,
      body: { tweetId: SUBJECT_TWEET_ID },
      status: 200,
      violations: [],
    });
  });
});

describe('generateTweetResponse: rejected disposition', () => {
  it('discards the original error instance rather than re-throwing it, unlike twitterService', async () => {
    // Absorbs the subject's own log line; the next test is the one that asserts it.
    jest.spyOn(console, 'error').mockImplementation(() => undefined);
    const boom = new Error('boom');
    jest.spyOn(axios, 'post').mockRejectedValue(boom);

    const caught = await generateTweetResponse(SUBJECT_TWEET_ID).catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    // Exactly this message, with nothing of the original appended to it.
    expect((caught as Error).message).toBe(REPLACEMENT_ERROR_MESSAGE);
    // A different instance from the one that caused it: the original is not propagated.
    expect(caught).not.toBe(boom);
  });

  it('logs the original error next to its prefix before replacing it', async () => {
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    const boom = new Error('boom');
    jest.spyOn(axios, 'post').mockRejectedValue(boom);

    await expect(generateTweetResponse(SUBJECT_TWEET_ID)).rejects.toBeInstanceOf(Error);

    expect(consoleError).toHaveBeenCalledTimes(1);

    const call = consoleError.mock.calls[0];

    expect(call).toHaveLength(2);
    expect(call[0]).toBe(LOG_PREFIX);
    // The original instance, by identity: it is logged even though it is not thrown.
    expect(call[1]).toBe(boom);
  });

  it('replaces a rejection from the real transport the same way, losing the AxiosError', async () => {
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    // The route as the assembled backend answers it today: 404, because no router declares the path.
    server.use(...currentBehaviorGenerateResponseHandlers());

    const caught = await generateTweetResponse(SUBJECT_TWEET_ID).catch((error: unknown) => error);

    expect(lastRecordedRequest()).toMatchObject({ status: BACKEND_NOT_FOUND_STATUS, violations: [] });

    expect(caught).toBeInstanceOf(Error);
    expect((caught as Error).message).toBe(REPLACEMENT_ERROR_MESSAGE);
    // The thrown error carries nothing of the transport failure: it is not the AxiosError.
    expect((caught as { isAxiosError?: unknown }).isAxiosError).toBeUndefined();

    // The AxiosError itself went to the log, which is the only place it survives.
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect((consoleError.mock.calls[0][1] as { isAxiosError?: unknown }).isAxiosError).toBe(true);
  });
});

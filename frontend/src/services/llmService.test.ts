import axios from 'axios';

import { generateTweetResponse } from './llmService';
import {
  BACKEND_NOT_FOUND_STATUS,
  DEFAULT_GENERATED_RESPONSE,
  lastRecordedRequest,
  recordedRequests,
  unsetBaseBackendHandlers,
} from '../test-utils/handlers';
import { server } from '../test-utils/msw-server';

const SUBJECT_TWEET_ID = 'tweet-1';

const REPLACEMENT_ERROR_MESSAGE = 'Failed to generate tweet response';

const LOG_PREFIX = 'Error generating tweet response:';

const REQUEST_PATHNAME = '/undefined/generate-response';

const SPIED_GENERATED_RESPONSE = 'hello';

/** Restore axios.post and console.error spies so settled outcomes do not leak between tests. */
afterEach(() => {
  jest.restoreAllMocks();
});

describe('generateTweetResponse: resolved disposition', () => {
  it('resolves with the generated response the API layer unwrapped, over the real transport', async () => {
    const result = await generateTweetResponse(SUBJECT_TWEET_ID);

    expect(result).toBe(DEFAULT_GENERATED_RESPONSE);

    expect(recordedRequests()).toHaveLength(1);
  });

  it('returns the value the API layer produced verbatim, without inspecting or transforming it', async () => {
    const post = jest
      .spyOn(axios, 'post')
      .mockResolvedValue({ data: { generatedResponse: SPIED_GENERATED_RESPONSE } });

    const result = await generateTweetResponse(SUBJECT_TWEET_ID);

    expect(result).toBe(SPIED_GENERATED_RESPONSE);
    expect(post).toHaveBeenCalledTimes(1);

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
    jest.spyOn(console, 'error').mockImplementation(() => undefined);
    const boom = new Error('boom');
    jest.spyOn(axios, 'post').mockRejectedValue(boom);

    const caught = await generateTweetResponse(SUBJECT_TWEET_ID).catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(Error);
    expect((caught as Error).message).toBe(REPLACEMENT_ERROR_MESSAGE);
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
    expect(call[1]).toBe(boom);
  });

  it('replaces a rejection from the real transport the same way, losing the AxiosError', async () => {
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    // 404 for two independent reasons that both hold: the emitted path carries the unrouted `/undefined`
    // prefix, and `/generate-response` is declared by no router under any base. So this is the one route
    // whose 404 survives configuring the base URL.
    server.use(...unsetBaseBackendHandlers());

    const caught = await generateTweetResponse(SUBJECT_TWEET_ID).catch((error: unknown) => error);

    expect(lastRecordedRequest()).toMatchObject({ status: BACKEND_NOT_FOUND_STATUS, violations: [] });

    expect(caught).toBeInstanceOf(Error);
    expect((caught as Error).message).toBe(REPLACEMENT_ERROR_MESSAGE);
    expect((caught as { isAxiosError?: unknown }).isAxiosError).toBeUndefined();

    expect(consoleError).toHaveBeenCalledTimes(1);
    expect((consoleError.mock.calls[0][1] as { isAxiosError?: unknown }).isAxiosError).toBe(true);
  });
});

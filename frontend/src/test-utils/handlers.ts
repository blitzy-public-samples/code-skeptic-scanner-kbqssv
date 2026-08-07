/**
 * Default msw request handlers for the frontend Jest suite.
 *
 * `src/test-utils/msw-server.ts` passes the `handlers` array exported here to
 * `setupServer`, and `src/test-utils/setup-jest.ts` starts that server with
 * `onUnhandledRequest: 'error'`, so a request to a route this array does not
 * cover fails the test that issued it.
 *
 * The module provides:
 *
 * - `handlers` - one entry per HTTP route: the three routes `src/services/api.ts`
 *   requests, plus the tweet-responses endpoint implemented by
 *   `backend/app/api/routes/tweets.py`.
 * - `DEFAULT_TWEETS` - the tweets the tweet-collection handler returns.
 * - `DEFAULT_TWEETS_JSON` - `DEFAULT_TWEETS` in the shape it takes on the wire.
 * - `DEFAULT_GENERATED_RESPONSE` - the string the generate-response handler
 *   returns.
 * - `DEFAULT_TWEET_RESPONSE` - the string the tweet-responses handler returns.
 * - `SerializedTweet` - the element type of `DEFAULT_TWEETS_JSON`.
 *
 * Every pattern below is prefixed with a `*` wildcard and matches on path alone.
 * `src/services/api.ts` reads its base URL from
 * `process.env.REACT_APP_API_BASE_URL`, which is unset under Jest, so the URLs
 * that reach msw are of the form `undefined/tweets?page=2&limit=10`.
 * `getLatestTweets(count)` in `src/services/twitterService.ts` passes one
 * argument to the two-parameter `fetchTweets`, so the query string it emits is
 * `?page=<count>&limit=undefined`. No pattern here encodes a host or a query
 * string.
 *
 * This module registers handlers only: `setupServer` and every server lifecycle
 * call live in `src/test-utils/msw-server.ts` and `src/test-utils/setup-jest.ts`.
 *
 * msw 1.x API - handlers are built with `rest`, and a resolver has the form
 * `(req, res, ctx) => res(ctx.status(...), ctx.json(...))`.
 *
 * Frontend testing conventions and the msw contract: `frontend/TESTING.md`.
 * Recorded design decisions: `docs/testing/DECISION-LOG.md`.
 */

import { rest } from 'msw';
import type { RestHandler } from 'msw';

import { makeTweet } from './factories';

/**
 * The tweet shape `makeTweet` in `src/test-utils/factories.ts` produces: the ten
 * fields declared by `src/schema/tweetSchema.ts`, with `timestamp` a `Date`.
 */
type TweetFixture = ReturnType<typeof makeTweet>;

/**
 * A `TweetFixture` after JSON serialisation.
 *
 * `ctx.json` serialises the `Date` that `makeTweet` puts in `timestamp` to an
 * ISO-8601 string, so this is the shape a caller of `src/services/api.ts`
 * receives.
 */
export type SerializedTweet = Omit<TweetFixture, 'timestamp'> & {
  timestamp: string;
};

/**
 * The string the generate-response handler returns under the
 * `generatedResponse` key.
 *
 * `generateResponse` in `src/services/api.ts` returns
 * `response.data.generatedResponse`, and `generateTweetResponse` in
 * `src/services/llmService.ts` returns that value unchanged, so both resolve to
 * this string.
 */
export const DEFAULT_GENERATED_RESPONSE =
  'Benchmark the assistant on your own repository before drawing a conclusion.';

/**
 * The string the tweet-responses handler returns under the `response` key.
 *
 * `POST /tweets/{tweet_id}/responses` in `backend/app/api/routes/tweets.py`
 * returns its generated text under that key.
 */
export const DEFAULT_TWEET_RESPONSE = 'Draft reply stored for review.';

/**
 * The tweets the tweet-collection handler returns.
 *
 * Every element comes from `makeTweet`, so all three satisfy `tweetSchema` in
 * full. Element 0 is `makeTweet()` with no overrides; elements 1 and 2 override
 * `tweet_id` and a different subset of the remaining fields, so a suite can tell
 * them apart by index.
 */
export const DEFAULT_TWEETS: TweetFixture[] = [
  makeTweet(),
  makeTweet({
    tweet_id: 'tweet-2',
    content: 'Every AI pair-programming demo I have seen quietly skips the debugging.',
    user_id: 'user-2',
    likes_count: 5,
    retweets_count: 1,
    doubt_rating: 0.35,
    ai_tools: ['ChatGPT'],
  }),
  makeTweet({
    tweet_id: 'tweet-3',
    content: 'The assistant wrote the test and the bug. Impressive symmetry.',
    user_id: 'user-3',
    likes_count: 0,
    retweets_count: 0,
    doubt_rating: 0.95,
    ai_tools: ['Copilot', 'ChatGPT'],
    media_urls: ['https://example.invalid/media/tweet-3.png'],
    quoted_tweet_id: 'tweet-1',
  }),
];

/**
 * `DEFAULT_TWEETS` in the shape it takes on the wire, with every `timestamp`
 * an ISO-8601 string.
 *
 * This is what `fetchTweets` in `src/services/api.ts` resolves to. It is derived
 * from `DEFAULT_TWEETS` and rebuilds the array members, so the two constants
 * share no mutable state.
 */
export const DEFAULT_TWEETS_JSON: SerializedTweet[] = DEFAULT_TWEETS.map((tweet) => ({
  ...tweet,
  ai_tools: [...tweet.ai_tools],
  media_urls: [...tweet.media_urls],
  timestamp: tweet.timestamp.toISOString(),
}));

/**
 * The default handler array `src/test-utils/msw-server.ts` passes to
 * `setupServer`.
 *
 * One entry per route, in `/tweets` order followed by the standalone
 * generate-response route. Adding a route is one more `rest.<method>(...)`
 * entry: no entry reads, wraps or branches through another.
 */
export const handlers: RestHandler[] = [
  /**
   * `GET /tweets` - requested by `fetchTweets(page, limit)` in
   * `src/services/api.ts`, and through it by `getLatestTweets(count)` in
   * `src/services/twitterService.ts`.
   *
   * Returns `DEFAULT_TWEETS`, the ten-field shape of
   * `src/schema/tweetSchema.ts` that `fetchTweets` casts `response.data` to. The
   * `{ id, text }` shape of `makeFeedTweet` is a separate fixture and is not
   * merged into this payload.
   */
  rest.get('*/tweets', (_req, res, ctx) => res(ctx.status(200), ctx.json(DEFAULT_TWEETS))),

  /**
   * `GET /tweets/:tweetId` - requested by `fetchTweetById(tweetId)` in
   * `src/services/api.ts`, and through it by `getTweetDetails(tweetId)` in
   * `src/services/twitterService.ts`.
   *
   * Returns one tweet whose `tweet_id` is the `:tweetId` path parameter of the
   * request; every other field is the `makeTweet` default.
   */
  rest.get<never, { tweetId: string }>('*/tweets/:tweetId', (req, res, ctx) =>
    res(ctx.status(200), ctx.json(makeTweet({ tweet_id: req.params.tweetId }))),
  ),

  /**
   * `POST /tweets/:tweetId/responses` - the endpoint
   * `backend/app/api/routes/tweets.py` implements, which returns its generated
   * text under the `response` key. No module under `src/` requests it.
   */
  rest.post('*/tweets/:tweetId/responses', (_req, res, ctx) =>
    res(ctx.status(201), ctx.json({ response: DEFAULT_TWEET_RESPONSE })),
  ),

  /**
   * `POST /generate-response` - requested by `generateResponse(tweetId)` in
   * `src/services/api.ts` with a `{ tweetId }` body.
   *
   * `generateResponse` returns `response.data.generatedResponse`, so the body
   * carries `DEFAULT_GENERATED_RESPONSE` under the `generatedResponse` key.
   */
  rest.post('*/generate-response', (_req, res, ctx) =>
    res(ctx.status(200), ctx.json({ generatedResponse: DEFAULT_GENERATED_RESPONSE })),
  ),
];

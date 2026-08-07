/**
 * Default msw request handlers for the frontend Jest suite: one entry per HTTP route, covering the three
 * routes `src/services/api.ts` requests plus the tweet-responses endpoint the backend implements. This
 * module registers handlers only - it constructs no server and makes no lifecycle call.
 *
 * Every pattern is prefixed with a `*` wildcard and matches on path alone, because
 * `src/services/api.ts` reads its base URL from an unset `process.env.REACT_APP_API_BASE_URL`, so the URLs
 * reaching msw are of the form `undefined/tweets?page=2&limit=10`, and `getLatestTweets(count)` passes one
 * argument to the two-parameter `fetchTweets`, emitting `?page=<count>&limit=undefined`.
 *
 * The two tweet payloads are builders rather than arrays and every resolver calls one per request, so no
 * two responses share an object; the two exported response strings are primitives and immutable already.
 *
 * msw 1.x API - handlers are built with `rest`, resolvers have the form
 * `(req, res, ctx) => res(ctx.status(...), ctx.json(...))`.
 */

import { rest } from 'msw';
import type { RestHandler } from 'msw';

import { makeTweet } from './factories';

type TweetFixture = ReturnType<typeof makeTweet>;

/** After JSON serialisation `timestamp` is an ISO-8601 string, so this is the shape a caller receives. */
export type SerializedTweet = Omit<TweetFixture, 'timestamp'> & {
  timestamp: string;
};

/**
 * One `TweetFixture` in the shape it takes on the wire. The array members are rebuilt, so the returned
 * object shares nothing with the tweet it was derived from.
 */
function serializeTweet(tweet: TweetFixture): SerializedTweet {
  return {
    ...tweet,
    ai_tools: [...tweet.ai_tools],
    media_urls: [...tweet.media_urls],
    timestamp: tweet.timestamp.toISOString(),
  };
}

/** Returned under the `generatedResponse` key, which both `generateResponse` and `generateTweetResponse` resolve to. */
export const DEFAULT_GENERATED_RESPONSE =
  'Benchmark the assistant on your own repository before drawing a conclusion.';

/** Returned under the `response` key, as the backend's tweet-responses route does. */
export const DEFAULT_TWEET_RESPONSE = 'Draft reply stored for review.';

/**
 * The tweets the tweet-collection handler returns. Every element comes from `makeTweet`, so all three
 * satisfy `tweetSchema` in full, and elements 1 and 2 override a different subset of fields so a suite can
 * tell them apart by index.
 *
 * A function rather than an array: the tweets are rebuilt on every call, so each request is handed its own
 * objects and a suite that mutates a response changes nothing for the next one.
 *
 * @returns Three freshly built, schema-valid tweets.
 */
export function makeDefaultTweets(): TweetFixture[] {
  return [
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
}

/**
 * `makeDefaultTweets()` in the shape it takes on the wire, with every `timestamp` an ISO-8601 string; this
 * is what `fetchTweets` resolves to, so it is the value a suite asserts the resolved payload against.
 *
 * @returns Three freshly built tweets in their serialised form.
 */
export function makeDefaultTweetsJson(): SerializedTweet[] {
  return makeDefaultTweets().map(serializeTweet);
}

/**
 * The default handler array, in `/tweets` order followed by the standalone generate-response route. Adding
 * a route is one more `rest.<method>(...)` entry: no entry reads, wraps or branches through another, and
 * every resolver builds its payload inside itself.
 */
export const handlers: RestHandler[] = [
  /**
   * `GET /tweets` - requested by `fetchTweets(page, limit)`, and through it by `getLatestTweets(count)`.
   * The `{ id, text }` shape of `makeFeedTweet` is a separate fixture and is not merged into this payload.
   */
  rest.get('*/tweets', (_req, res, ctx) => res(ctx.status(200), ctx.json(makeDefaultTweets()))),

  /**
   * `GET /tweets/:tweetId` - requested by `fetchTweetById(tweetId)`, and through it by
   * `getTweetDetails(tweetId)`. The returned `tweet_id` is the path parameter of the request.
   */
  rest.get<never, { tweetId: string }>('*/tweets/:tweetId', (req, res, ctx) =>
    res(ctx.status(200), ctx.json(makeTweet({ tweet_id: req.params.tweetId }))),
  ),

  /**
   * `POST /tweets/:tweetId/responses` - implemented by the backend, which returns its generated text under
   * the `response` key; no module under `src/` requests it. The status is `200`: the route is declared with
   * no `status_code`, so FastAPI answers with its default rather than a `201`.
   */
  rest.post('*/tweets/:tweetId/responses', (_req, res, ctx) =>
    res(ctx.status(200), ctx.json({ response: DEFAULT_TWEET_RESPONSE })),
  ),

  /** `POST /generate-response` - requested by `generateResponse(tweetId)` with a `{ tweetId }` body. */
  rest.post('*/generate-response', (_req, res, ctx) =>
    res(ctx.status(200), ctx.json({ generatedResponse: DEFAULT_GENERATED_RESPONSE })),
  ),
];

/**
 * Fixture builders for the frontend Jest suite.
 *
 * This module is the single definition point for the tweet and user test data
 * consumed by the colocated `*.test.ts` and `*.test.tsx` suites. It provides:
 *
 * - `makeTweet` - the ten-field `Tweet` declared by `src/schema/tweetSchema.ts`.
 * - `makeUser` - the five-field `User` declared by `src/schema/userSchema.ts`.
 * - `makeFeedTweet` - the separate `{ id, text }` shape that the tweet list
 *   components render and key on.
 * - `FIXED_TWEET_TIMESTAMP` and `FIXED_USER_CREATED_AT` - the fixed instants the
 *   builders emit, available for suites to assert against.
 *
 * Every builder takes an optional `overrides` object that is applied last, and
 * returns a new object whose `Date` and array members are fresh instances on
 * every call.
 *
 * `src/schema/tweetSchema.test.ts` and `src/schema/userSchema.test.ts` parse
 * `makeTweet()` and `makeUser()` through the real zod schemas.
 *
 * Usage and the wider frontend testing conventions: `frontend/TESTING.md`.
 * Recorded design decisions: `docs/testing/DECISION-LOG.md`.
 */

import type { Tweet } from '../schema/tweetSchema';
import type { User } from '../schema/userSchema';

/**
 * ISO-8601 instant backing every `Tweet.timestamp` produced by this module.
 */
const TWEET_TIMESTAMP_ISO = '2024-01-15T12:00:00.000Z';

/**
 * ISO-8601 instant backing every `User.created_at` produced by this module.
 */
const USER_CREATED_AT_ISO = '2023-06-01T08:30:00.000Z';

/**
 * Body text carried by both tweet fixtures, so the two shapes describe the
 * same notional tweet.
 */
const TWEET_TEXT = 'Not convinced AI coding assistants actually save anyone time.';

/**
 * The `timestamp` carried by `makeTweet()` when it is not overridden.
 *
 * Suites compare against this constant. Each call to `makeTweet()` rebuilds its
 * own `Date` from the underlying literal, so this instance is never handed out
 * and cannot be mutated through a fixture.
 */
export const FIXED_TWEET_TIMESTAMP = new Date(TWEET_TIMESTAMP_ISO);

/**
 * The `created_at` carried by `makeUser()` when it is not overridden.
 *
 * As with `FIXED_TWEET_TIMESTAMP`, `makeUser()` rebuilds its own `Date` and
 * never hands out this instance.
 */
export const FIXED_USER_CREATED_AT = new Date(USER_CREATED_AT_ISO);

/**
 * The tweet shape rendered by the feed and list components, which key on `id`.
 *
 * Distinct from the `Tweet` of `src/schema/tweetSchema.ts`, which declares no
 * `id` field. The two shapes are not interchangeable.
 */
export interface FeedTweet {
  id: string;
  text: string;
}

/**
 * Builds a `Tweet` that satisfies `tweetSchema` in full.
 *
 * All ten fields are populated. `quoted_tweet_id` is always present because the
 * schema field is nullable rather than optional: `null` is accepted, an absent
 * key is not. `timestamp` is a real `Date`, which the schema requires; an
 * ISO string in its place is rejected.
 *
 * @param overrides - Fields to replace on the returned tweet.
 * @returns A schema-valid `Tweet` with fresh `Date` and array members.
 */
export function makeTweet(overrides: Partial<Tweet> = {}): Tweet {
  return {
    tweet_id: 'tweet-1',
    content: TWEET_TEXT,
    user_id: 'user-1',
    timestamp: new Date(TWEET_TIMESTAMP_ISO),
    likes_count: 42,
    retweets_count: 7,
    doubt_rating: 0.8,
    ai_tools: ['Copilot'],
    media_urls: [],
    quoted_tweet_id: null,
    ...overrides,
  };
}

/**
 * Builds a `User` that satisfies `userSchema` in full.
 *
 * All five fields are populated, and `created_at` is a real `Date` as the schema
 * requires. `user_id` matches the `user_id` of `makeTweet()`, so a suite can pair
 * the two fixtures without overriding either.
 *
 * @param overrides - Fields to replace on the returned user.
 * @returns A schema-valid `User` with a fresh `created_at` instance.
 */
export function makeUser(overrides: Partial<User> = {}): User {
  return {
    user_id: 'user-1',
    username: 'skeptic_dev',
    display_name: 'Skeptic Dev',
    followers_count: 1234,
    created_at: new Date(USER_CREATED_AT_ISO),
    ...overrides,
  };
}

/**
 * Builds a `FeedTweet`, the `{ id, text }` shape the tweet list components
 * render.
 *
 * The schema `Tweet` declares no `id`, so a fixture for one shape never
 * satisfies the other.
 *
 * @param overrides - Fields to replace on the returned feed tweet.
 * @returns A `FeedTweet` carrying a stable synthetic `id` and `text`.
 */
export function makeFeedTweet(overrides: Partial<FeedTweet> = {}): FeedTweet {
  return {
    id: 'feed-tweet-1',
    text: TWEET_TEXT,
    ...overrides,
  };
}

/**
 * Fixture builders for the frontend Jest suite: the single definition point for
 * the tweet and user test data the colocated suites consume.
 *
 * Each builder applies its optional `overrides` last and returns a new object whose `Date`, array and
 * nested-object members are fresh instances - including the ones supplied through `overrides`, which are
 * copied rather than aliased. Nothing this module exports is a shared mutable value.
 *
 * `FIXED_TWEET_TIMESTAMP` and `FIXED_USER_CREATED_AT` are the ISO-8601 literals the builders emit, as
 * immutable strings; `fixedTweetTimestamp()` and `fixedUserCreatedAt()` return those instants as `Date`s.
 */

import type { Tweet } from '../schema/tweetSchema';
import type { User } from '../schema/userSchema';

/** ISO-8601 literal behind every `Tweet.timestamp` this module produces; a primitive, so it cannot be mutated. */
export const FIXED_TWEET_TIMESTAMP = '2024-01-15T12:00:00.000Z';

/** ISO-8601 literal behind every `User.created_at` this module produces, on the same terms. */
export const FIXED_USER_CREATED_AT = '2023-06-01T08:30:00.000Z';

const TWEET_TEXT = 'Not convinced AI coding assistants actually save anyone time.';

/**
 * The `timestamp` `makeTweet()` emits when it is not overridden.
 *
 * @returns A new `Date` at {@link FIXED_TWEET_TIMESTAMP} on every call.
 */
export function fixedTweetTimestamp(): Date {
  return new Date(FIXED_TWEET_TIMESTAMP);
}

/**
 * The `created_at` `makeUser()` emits when it is not overridden.
 *
 * @returns A new `Date` at {@link FIXED_USER_CREATED_AT} on every call.
 */
export function fixedUserCreatedAt(): Date {
  return new Date(FIXED_USER_CREATED_AT);
}

/**
 * A deep copy of one fixture member. `Date` objects and arrays are rebuilt and plain objects are rebuilt
 * member by member; primitives, `null` and anything with a non-plain prototype are returned unchanged, which
 * leaves a non-`Date` override intact.
 */
function cloneMember(value: unknown): unknown {
  if (value instanceof Date) {
    return new Date(value.getTime());
  }

  if (Array.isArray(value)) {
    return value.map(cloneMember);
  }

  if (typeof value === 'object' && value !== null) {
    const prototype = Object.getPrototypeOf(value);
    if (prototype === Object.prototype || prototype === null) {
      return cloneFixture(value as Record<string, unknown>);
    }
  }

  return value;
}

/**
 * A fixture whose every member is a fresh instance. Each builder passes its base-plus-overrides object
 * through here, so a `Date` or array handed in through `overrides` is copied rather than aliased.
 */
function cloneFixture<T extends object>(fixture: T): T {
  const cloned: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(fixture)) {
    cloned[key] = cloneMember(value);
  }
  return cloned as T;
}

/**
 * The shape the feed and list components render and key on. The schema `Tweet`
 * declares no `id`, so the two shapes are not interchangeable.
 */
export interface FeedTweet {
  id: string;
  text: string;
}

/**
 * Builds a `Tweet` that satisfies `tweetSchema` in full. `timestamp` is a real
 * `Date`, which the schema requires and an ISO string cannot satisfy, and
 * `quoted_tweet_id` is always present because the field is nullable rather than
 * optional: `null` is accepted, an absent key is not.
 *
 * @param overrides - Fields to replace on the returned tweet; any `Date` or array supplied here is copied.
 * @returns A schema-valid `Tweet` whose every `Date` and array member is a fresh instance.
 */
export function makeTweet(overrides: Partial<Tweet> = {}): Tweet {
  return cloneFixture({
    tweet_id: 'tweet-1',
    content: TWEET_TEXT,
    user_id: 'user-1',
    timestamp: fixedTweetTimestamp(),
    likes_count: 42,
    retweets_count: 7,
    doubt_rating: 0.8,
    ai_tools: ['Copilot'],
    media_urls: [],
    quoted_tweet_id: null,
    ...overrides,
  });
}

/**
 * Builds a `User` that satisfies `userSchema` in full, with `created_at` a real
 * `Date`. Its `user_id` matches the `user_id` of `makeTweet()`, so the two
 * fixtures pair without either being overridden.
 *
 * @param overrides - Fields to replace on the returned user; a `Date` supplied here is copied.
 * @returns A schema-valid `User` with a fresh `created_at` instance.
 */
export function makeUser(overrides: Partial<User> = {}): User {
  return cloneFixture({
    user_id: 'user-1',
    username: 'skeptic_dev',
    display_name: 'Skeptic Dev',
    followers_count: 1234,
    created_at: fixedUserCreatedAt(),
    ...overrides,
  });
}

/**
 * Builds a {@link FeedTweet} carrying a stable synthetic `id` and `text`, freshly allocated on every call.
 *
 * @param overrides - Fields to replace on the returned feed tweet.
 */
export function makeFeedTweet(overrides: Partial<FeedTweet> = {}): FeedTweet {
  return cloneFixture({
    id: 'feed-tweet-1',
    text: TWEET_TEXT,
    ...overrides,
  });
}

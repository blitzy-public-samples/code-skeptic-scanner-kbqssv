/**
 * Unit suite for `src/schema/tweetSchema.ts`, colocated beside its subject.
 *
 * This suite is the primary half of the fixture-honesty gate. It parses the output of the shared
 * `makeTweet()` builder through the real `tweetSchema`, so a fixture that drifts away from the
 * schema's ten-field contract fails here rather than silently weakening every other frontend
 * suite that builds its data from the same factory.
 *
 * Three properties of the schema as it stands today bound what is assertable, and each is pinned
 * below rather than corrected:
 *
 * 1. `timestamp` is `z.date()`, so a raw JSON payload can never satisfy the schema - the shape the
 *    API returns and the shape this schema validates are permanently incompatible.
 * 2. `quoted_tweet_id` is `z.string().nullable()`, which admits the value `null` but not an absent
 *    key: nullable is not optional.
 * 3. The schema is a plain `z.object(...)` with no `.strict()`, so an unknown key is stripped from
 *    the parsed result and never reported as an issue. No unknown-key rejection behaviour exists to
 *    be asserted.
 *
 * The trailing comments in the subject name validation that was never implemented - a maximum
 * content length, a 0-100 range for `doubt_rating`, and identifier-format checks. No test below
 * asserts any of it.
 *
 * @see frontend/TESTING.md - the factory contract this suite gates, and the msw lifecycle that
 *   `src/test-utils/setup-jest.ts` registers globally for every suite.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why the assertions below take
 *   the form they do.
 */

import { FIXED_TWEET_TIMESTAMP, makeTweet } from '../test-utils/factories';
import { tweetSchema } from './tweetSchema';

describe('src/schema/tweetSchema.ts — tweetSchema', () => {
  it('accepts the shared makeTweet() fixture and round-trips all ten fields', () => {
    const tweet = makeTweet();

    const result = tweetSchema.safeParse(tweet);

    expect(result.success).toBe(true);

    if (result.success) {
      expect(result.data.tweet_id).toBe('tweet-1');
      expect(result.data.content).toBe(
        'Not convinced AI coding assistants actually save anyone time.'
      );
      expect(result.data.user_id).toBe('user-1');

      /* `z.date()` yields a `Date`, at the instant the factory's exported literal names. */
      expect(result.data.timestamp).toBeInstanceOf(Date);
      expect(result.data.timestamp.toISOString()).toBe(FIXED_TWEET_TIMESTAMP);

      expect(result.data.likes_count).toBe(42);
      expect(result.data.retweets_count).toBe(7);
      expect(result.data.doubt_rating).toBe(0.8);

      expect(result.data.ai_tools).toEqual(['Copilot']);
      expect(result.data.media_urls).toEqual([]);

      expect(result.data.quoted_tweet_id).toBeNull();
    }
  });

  it('timestamp: rejects an ISO-8601 string because the field is z.date()', () => {
    /*
     * The string carries the exact instant `makeTweet()` emits as a `Date`: the rejection below is
     * driven by the type of the value, never by the instant it represents.
     */
    const withStringTimestamp = { ...makeTweet(), timestamp: FIXED_TWEET_TIMESTAMP };

    const result = tweetSchema.safeParse(withStringTimestamp);

    expect(result.success).toBe(false);

    if (!result.success) {
      expect(result.error.issues).toHaveLength(1);
      expect(result.error.issues[0]).toMatchObject({
        code: 'invalid_type',
        expected: 'date',
        received: 'string',
        path: ['timestamp'],
      });
    }
  });

  it('quoted_tweet_id: rejects an absent key because .nullable() is not .optional()', () => {
    const { quoted_tweet_id: _omitted, ...withoutQuotedTweetId } = makeTweet();

    const result = tweetSchema.safeParse(withoutQuotedTweetId);

    expect(result.success).toBe(false);

    if (!result.success) {
      expect(result.error.issues).toHaveLength(1);
      /* `.nullable()` reports the type it wraps, so `expected` is `string` rather than a union. */
      expect(result.error.issues[0]).toMatchObject({
        code: 'invalid_type',
        expected: 'string',
        received: 'undefined',
        path: ['quoted_tweet_id'],
      });
    }
  });

  it('quoted_tweet_id: accepts an explicit null because the field is .nullable()', () => {
    const result = tweetSchema.safeParse(makeTweet({ quoted_tweet_id: null }));

    expect(result.success).toBe(true);

    if (result.success) {
      expect(result.data.quoted_tweet_id).toBeNull();
    }
  });
});

import { FIXED_TWEET_TIMESTAMP, makeTweet } from '../test-utils/factories';
import { tweetSchema } from './tweetSchema';

/**
 * Every key `tweetSchema` declares, in declaration order.
 *
 * This is the contract the AAP protects, so it is stated here as a literal rather than derived from
 * the schema or from the factory: a list computed from either would agree with any change made to it.
 */
const DECLARED_KEYS = [
  'tweet_id',
  'content',
  'user_id',
  'timestamp',
  'likes_count',
  'retweets_count',
  'doubt_rating',
  'ai_tools',
  'media_urls',
  'quoted_tweet_id',
] as const;

/** A key no version of this schema has ever declared, used to probe unknown-key handling. */
const UNKNOWN_KEY = 'sentiment_score';

describe('src/schema/tweetSchema.ts — tweetSchema', () => {
  it('declares exactly the ten documented keys, and no others', () => {
    expect(Object.keys(tweetSchema.shape)).toEqual([...DECLARED_KEYS]);
    expect(Object.keys(tweetSchema.shape)).toHaveLength(DECLARED_KEYS.length);
  });

  it('strips an unknown key rather than rejecting it, because the object is not .strict()', () => {
    const withUnknownKey = { ...makeTweet(), [UNKNOWN_KEY]: 0.42 };

    const result = tweetSchema.safeParse(withUnknownKey);

    /* Accepted: a plain `z.object(...)` reports no issue for a key it does not declare. */
    expect(result.success).toBe(true);

    if (result.success) {
      /* And the key is absent from the output, so the parsed value carries the ten keys only. */
      expect(Object.keys(result.data)).toEqual([...DECLARED_KEYS]);
      expect(result.data).not.toHaveProperty(UNKNOWN_KEY);
    }
  });

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

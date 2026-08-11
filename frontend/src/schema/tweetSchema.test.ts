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

/**
 * One record exactly as `GET /tweets` emits it, transcribed from the response body
 * `backend/tests/integration/test_http_tweets.py` asserts.
 *
 * Written as a literal rather than built from `makeTweet()` on purpose: the point of this record is
 * that it is the *server's* shape, and a fixture-derived value would agree with the fixture instead.
 * Note `timestamp` - a JSON string with no `Z` and no offset, because `app/schema/tweet.py` declares
 * a bare `datetime` and nothing normalises the stored value.
 */
const BACKEND_RECORD = {
  tweet_id: '1234567890',
  content: 'Copilot will never write correct code.',
  user_id: 'skeptic_user',
  timestamp: '2024-01-01T00:00:00',
  likes_count: 10,
  retweets_count: 5,
  doubt_rating: 0.85,
  ai_tools: ['Copilot'],
  media_urls: ['https://example.invalid/a.png'],
  quoted_tweet_id: null,
} as const;

/** The hour named by {@link BACKEND_RECORD}'s timestamp, whichever zone reads it. */
const BACKEND_RECORD_LOCAL_HOUR = 0;

/** The offset-bearing form the same field emits when the stored value is timezone-aware. */
const BACKEND_AWARE_TIMESTAMP = '2024-02-02T00:00:00+02:00';

const MILLISECONDS_PER_MINUTE = 60_000;

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

  /**
   * The record above is a fixture. This block uses the record the backend genuinely emits, so the
   * mismatch is measured against production output rather than against a convenient stand-in.
   *
   * `backend/tests/integration/test_http_tweets.py` is the server-side oracle for every literal
   * here: the ten snake_case keys in this order, and a `timestamp` rendered with **no timezone
   * designator** because `app/schema/tweet.py` declares a bare `datetime` and the stored value is
   * naive.
   */
  describe('against the record the backend actually emits', () => {
    it('fails on exactly one field, and it is timestamp', () => {
      const result = tweetSchema.safeParse(BACKEND_RECORD);

      expect(result.success).toBe(false);

      if (!result.success) {
        /* One issue, not ten: every other field name and type already agrees with the backend. */
        expect(result.error.issues).toHaveLength(1);
        expect(result.error.issues[0]).toMatchObject({
          code: 'invalid_type',
          expected: 'date',
          received: 'string',
          path: ['timestamp'],
        });
      }
    });

    it('declares exactly the keys the backend emits, so the mismatch is one of type alone', () => {
      /*
       * Asserted as a set comparison in both directions: a schema key the backend omits and a
       * backend key the schema omits are different defects, and neither exists here.
       */
      expect(Object.keys(BACKEND_RECORD)).toEqual([...DECLARED_KEYS]);
    });

    it('accepts the same record once timestamp alone is coerced to a Date', () => {
      const coerced = { ...BACKEND_RECORD, timestamp: new Date(BACKEND_RECORD.timestamp) };

      const result = tweetSchema.safeParse(coerced);

      expect(result.success).toBe(true);

      if (result.success) {
        /* Coercing one field is sufficient: nothing else needed adjusting. */
        expect(Object.keys(result.data)).toEqual([...DECLARED_KEYS]);
        expect(result.data.tweet_id).toBe(BACKEND_RECORD.tweet_id);
        expect(result.data.likes_count).toBe(BACKEND_RECORD.likes_count);
        expect(result.data.quoted_tweet_id).toBeNull();
      }
    });

    it('coerces the zone-free string as LOCAL time, so the instant depends on the reader', () => {
      /*
       * The latent half of the same mismatch. Per ES2015 a date-time string carrying no designator
       * is parsed as local time, while a date-only string is parsed as UTC - so the coercion above
       * reconstructs a different instant in every timezone. This runs in whatever zone the host
       * offers, so the assertion is expressed as a relationship rather than as a fixed instant: the
       * coerced value equals the local reading, and it differs from the UTC reading by exactly the
       * host's offset.
       */
      const coerced = new Date(BACKEND_RECORD.timestamp);
      const asUtc = new Date(`${BACKEND_RECORD.timestamp}Z`);

      expect(coerced.getHours()).toBe(BACKEND_RECORD_LOCAL_HOUR);
      expect(asUtc.getUTCHours()).toBe(BACKEND_RECORD_LOCAL_HOUR);
      expect(coerced.getTime() - asUtc.getTime()).toBe(
        coerced.getTimezoneOffset() * MILLISECONDS_PER_MINUTE
      );
    });

    it('is the same schema that accepts an offset-bearing backend timestamp once coerced', () => {
      /*
       * The backend emits an offset when the stored value carries one - `test_http_tweets.py`
       * asserts `2024-02-02T00:00:00+02:00` - so a client cannot assume the zone-free form either.
       * Both forms are rejected as strings and both are accepted once coerced, which is why the fix
       * belongs at the boundary and not in a per-field special case.
       */
      const offsetBearing = { ...BACKEND_RECORD, timestamp: BACKEND_AWARE_TIMESTAMP };

      expect(tweetSchema.safeParse(offsetBearing).success).toBe(false);
      expect(
        tweetSchema.safeParse({ ...offsetBearing, timestamp: new Date(BACKEND_AWARE_TIMESTAMP) })
          .success
      ).toBe(true);
    });
  });
});

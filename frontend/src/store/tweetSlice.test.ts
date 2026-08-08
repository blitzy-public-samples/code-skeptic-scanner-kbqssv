import reducer, { addTweet, fetchTweets, updateTweet } from './tweetSlice';
import { makeTweet } from '../test-utils/factories';
import { makeStore } from '../test-utils/render';

type TweetState = ReturnType<typeof reducer>;

const THUNK_TYPE_PREFIX = 'tweets/fetchTweets';

const REQUEST_ID = 'test-request-id';

const REJECTION_MESSAGE = 'Failed to fetch tweets';

const REJECT_WITH_VALUE_ERROR_MESSAGE = 'Rejected';

const FIRST_TWEET_ID = 'tweet-first';
const SECOND_TWEET_ID = 'tweet-second';
const FIRST_CONTENT = 'The tweet seeded at index 0.';
const SECOND_CONTENT = 'The tweet seeded at index 1.';
const REPLACEMENT_CONTENT = 'The replacement addressed to the tweet seeded at index 1.';

function sliceStateWith(overrides: Partial<TweetState> = {}): TweetState {
  return { tweets: [], status: 'idle', error: null, ...overrides };
}

function seededPairAndReplacement() {
  return {
    first: makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT }),
    second: makeTweet({ tweet_id: SECOND_TWEET_ID, content: SECOND_CONTENT }),
    replacement: makeTweet({ tweet_id: SECOND_TWEET_ID, content: REPLACEMENT_CONTENT }),
  };
}

type FetchTweetsRejectedAction = ReturnType<typeof fetchTweets.rejected>;

async function dispatchFetchTweets(): Promise<{
  store: ReturnType<typeof makeStore>;
  action: FetchTweetsRejectedAction;
}> {
  const store = makeStore();
  const action = await store.dispatch(fetchTweets());

  if (!fetchTweets.rejected.match(action)) {
    throw new Error(
      `expected ${THUNK_TYPE_PREFIX}/rejected, but the thunk settled with ${action.type}`,
    );
  }

  return { store, action };
}

describe('tweetSlice: initial state', () => {
  it('starts with an empty tweet list, status "idle" and no error', () => {
    const state = reducer(undefined, { type: 'unknown/action' });

    expect(state).toEqual({ tweets: [], status: 'idle', error: null });
    expect(state.tweets).toEqual([]);
    expect(state.status).toBe('idle');
    expect(state.error).toBeNull();
  });
});

describe('tweetSlice: addTweet', () => {
  it('appends the tweet it is given, storing that exact object', () => {
    const tweet = makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT });

    const state = reducer(sliceStateWith(), addTweet(tweet));

    expect(state.tweets).toHaveLength(1);
    expect(state.tweets[0]).toEqual(tweet);
    expect(state.tweets[0]).toBe(tweet);
  });

  it('appends a second tweet after the first instead of replacing it', () => {
    const first = makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT });
    const second = makeTweet({ tweet_id: SECOND_TWEET_ID, content: SECOND_CONTENT });

    const state = reducer(reducer(sliceStateWith(), addTweet(first)), addTweet(second));

    expect(state.tweets).toHaveLength(2);
    expect(state.tweets[0]).toEqual(first);
    expect(state.tweets[1]).toEqual(second);
    expect(state.tweets.map((tweet) => tweet.content)).toEqual([FIRST_CONTENT, SECOND_CONTENT]);
  });

  it('leaves the state it was handed unchanged', () => {
    const seeded = sliceStateWith({ tweets: [makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT })] });
    const unchanged = sliceStateWith({ tweets: [makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT })] });

    const state = reducer(seeded, addTweet(makeTweet({ tweet_id: SECOND_TWEET_ID, content: SECOND_CONTENT })));

    expect(state.tweets).toHaveLength(2);
    expect(seeded).toEqual(unchanged);
    expect(seeded.tweets).toHaveLength(1);
  });
});

describe('tweetSlice: updateTweet', () => {
  it('overwrites the tweet at index 0, whichever tweet the payload addresses', () => {
    const { first, second, replacement } = seededPairAndReplacement();

    const state = reducer(sliceStateWith({ tweets: [first, second] }), updateTweet(replacement));

    expect(state.tweets).toHaveLength(2);
    expect(state.tweets[0]).toEqual(replacement);
    expect(state.tweets[0].tweet_id).toBe(SECOND_TWEET_ID);
    expect(state.tweets[0].content).toBe(REPLACEMENT_CONTENT);
    expect(state.tweets[0]).not.toEqual(first);
  });

  it('leaves the tweet the payload actually addresses untouched at index 1', () => {
    const { first, second, replacement } = seededPairAndReplacement();

    const state = reducer(sliceStateWith({ tweets: [first, second] }), updateTweet(replacement));

    expect(state.tweets[1]).toEqual(second);
    expect(state.tweets[1]).not.toEqual(replacement);
    expect(state.tweets[1].content).toBe(SECOND_CONTENT);
  });

  it('changes nothing when the tweet list is empty', () => {
    const state = reducer(sliceStateWith(), updateTweet(makeTweet({ tweet_id: FIRST_TWEET_ID })));

    expect(state.tweets).toEqual([]);
    expect(state.tweets).toHaveLength(0);
    expect(state.status).toBe('idle');
    expect(state.error).toBeNull();
  });
});

describe('tweetSlice: the fetchTweets status transition table', () => {
  it.each([
    {
      actionType: `${THUNK_TYPE_PREFIX}/pending`,
      expectedStatus: 'loading',
      settle: () => reducer(sliceStateWith(), fetchTweets.pending(REQUEST_ID)),
    },
    {
      actionType: `${THUNK_TYPE_PREFIX}/fulfilled`,
      expectedStatus: 'succeeded',
      settle: () => reducer(sliceStateWith(), fetchTweets.fulfilled([makeTweet()], REQUEST_ID)),
    },
    {
      actionType: `${THUNK_TYPE_PREFIX}/rejected`,
      expectedStatus: 'failed',
      settle: async () => (await dispatchFetchTweets()).store.getState().tweets,
    },
  ])('$actionType leaves the slice at status "$expectedStatus"', async ({ expectedStatus, settle }) => {
    const state = await settle();

    expect(state.status).toBe(expectedStatus);
  });

  it('pending sets status to "loading" and leaves the tweets and the error as they were', () => {
    const seeded = makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT });
    const previousError = 'a rejection recorded before this request started';

    const state = reducer(
      sliceStateWith({ tweets: [seeded], status: 'failed', error: previousError }),
      fetchTweets.pending(REQUEST_ID),
    );

    expect(state.status).toBe('loading');
    expect(state.tweets).toEqual([seeded]);
    expect(state.error).toBe(previousError);
  });

  it('fulfilled sets status to "succeeded" and adopts the payload array itself', () => {
    const payload = [
      makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT }),
      makeTweet({ tweet_id: SECOND_TWEET_ID, content: SECOND_CONTENT }),
    ];

    const state = reducer(sliceStateWith(), fetchTweets.fulfilled(payload, REQUEST_ID));

    expect(state.status).toBe('succeeded');
    expect(state.tweets).toHaveLength(2);
    expect(state.tweets).toEqual(payload);
    expect(state.tweets).toBe(payload);
    // Lines 51-54 touch `status` and `tweets` only, so `error` is left exactly as it was found -
    // here the `null` the initial state carries.
    expect(state.error).toBeNull();
  });

  it('fulfilled retains an error recorded by an earlier rejection', () => {
    const payload = [makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT })];

    // The state a rejected request leaves behind, which is what the next request fulfils from.
    const state = reducer(
      sliceStateWith({ status: 'failed', error: REJECTION_MESSAGE }),
      fetchTweets.fulfilled(payload, REQUEST_ID),
    );

    expect(state.status).toBe('succeeded');
    expect(state.tweets).toBe(payload);
    /*
     * The current behaviour, and a divergence: the fulfilled case reducer assigns `status` and
     * `tweets` and never clears `error`, so a consumer rendering `error` alongside a `'succeeded'`
     * status shows the previous failure's message next to fresh data. Asserted rather than
     * corrected - clearing it would be a production change, and the previous version of this suite
     * asserted only `status` and `tweets`, so either disposition would have passed.
     */
    expect(state.error).toBe(REJECTION_MESSAGE);
  });

  it('fulfilled replaces the tweets already in the slice instead of appending to them', () => {
    const existing = makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT });
    const payload = [makeTweet({ tweet_id: SECOND_TWEET_ID, content: SECOND_CONTENT })];

    const state = reducer(
      sliceStateWith({ tweets: [existing], status: 'succeeded' }),
      fetchTweets.fulfilled(payload, REQUEST_ID),
    );

    expect(state.tweets).toHaveLength(1);
    expect(state.tweets).toEqual(payload);
    expect(state.tweets).not.toContainEqual(existing);
    expect(state.error).toBeNull();
  });
});

describe('tweetSlice: fetchTweets dispatched through a real store', () => {
  it('settles as rejected, carrying the message as the action payload rather than as an error message', async () => {
    const { action } = await dispatchFetchTweets();

    expect(action.type).toBe(`${THUNK_TYPE_PREFIX}/rejected`);
    expect(action.payload).toBe(REJECTION_MESSAGE);
    expect(action.meta.rejectedWithValue).toBe(true);
    expect(action.error.message).toBe(REJECT_WITH_VALUE_ERROR_MESSAGE);
  });

  it('sets status to "failed"', async () => {
    const { store } = await dispatchFetchTweets();

    expect(store.getState().tweets.status).toBe('failed');
  });

  it('records the rejection message in error', async () => {
    const { store } = await dispatchFetchTweets();

    expect(store.getState().tweets.error).toBe(REJECTION_MESSAGE);
  });

  it('leaves the tweet list empty', async () => {
    const { store } = await dispatchFetchTweets();

    expect(store.getState().tweets.tweets).toEqual([]);
    expect(store.getState().tweets.tweets).toHaveLength(0);
  });

  it('keeps the tweets already in the slice when its rejected action is applied to them', async () => {
    const { action } = await dispatchFetchTweets();
    const seeded = makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT });

    const state = reducer(sliceStateWith({ tweets: [seeded], status: 'loading' }), action);

    expect(state.tweets).toEqual([seeded]);
    expect(state.status).toBe('failed');
    expect(state.error).toBe(REJECTION_MESSAGE);
  });

  it('is at status "loading" from the moment it is dispatched until it settles', async () => {
    const store = makeStore();

    const settled = store.dispatch(fetchTweets());
    expect(store.getState().tweets.status).toBe('loading');

    await settled;

    expect(store.getState().tweets.status).toBe('failed');
  });
});

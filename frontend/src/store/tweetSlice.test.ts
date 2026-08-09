import reducer, { addTweet, fetchTweets, updateTweet } from './tweetSlice';
import * as apiModule from '../services/api';
import { makeTweet } from '../test-utils/factories';
import { makeStore } from '../test-utils/render';

type TweetState = ReturnType<typeof reducer>;

const THUNK_TYPE_PREFIX = 'tweets/fetchTweets';

/**
 * Shape of the `api` binding `tweetSlice.ts` line 3 imports from `../services/api`.
 *
 * That module declares `fetchTweets`, `fetchTweetById` and `generateResponse`, and no `api`, so the
 * binding resolves to `undefined` and the thunk's `api.get('/tweets')` at line 12 throws before any
 * request is built. Every other case in this file asserts the rejection that follows; the suite below
 * supplies the missing collaborator so lines 12-13 - the request and the `response.data` it returns -
 * can be exercised at all.
 */
type ApiCollaborator = { get: jest.Mock };

/** The module namespace with the collaborator the source expects to find on it. */
type ApiModuleWithCollaborator = typeof apiModule & { api?: ApiCollaborator };

/** Path `tweetSlice.ts` line 12 passes to `api.get`. */
const THUNK_REQUEST_PATH = '/tweets';

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

describe('tweetSlice: fetchTweets once the missing api collaborator is supplied', () => {
  let get: jest.Mock;
  let errorSpy: jest.SpyInstance;

  beforeEach(() => {
    /*
     * These are the only cases here that put real tweets into a real store, which is what makes Redux
     * Toolkit's serializability check speak: `tweetSchema` declares `timestamp` as `z.date()`, so a
     * schema-valid tweet carries a `Date` and can never be serializable state. `makeStore` keeps
     * `configureStore`'s default middleware deliberately, so the notice is expected - it is recorded
     * here and asserted below rather than left in the run's output.
     */
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    /*
     * Injected on the module namespace rather than through `jest.mock`, so `src/services/api.ts` is the
     * real module and only the one binding it fails to export is supplied. Under the CommonJS emit this
     * suite runs against, that namespace is the same object `tweetSlice.ts` reads `api` from, so the
     * assignment is what the thunk sees at call time. The same idiom attaches the missing `getTweets`
     * export in `src/components/TweetManagement.test.tsx`.
     */
    get = jest.fn();
    (apiModule as ApiModuleWithCollaborator).api = { get };
  });

  afterEach(() => {
    /* Removed again, so every other case in this file still observes the real `undefined` binding. */
    delete (apiModule as ApiModuleWithCollaborator).api;
    errorSpy.mockRestore();
  });

  /** Every recorded `console.error` whose first argument mentions a non-serializable value. */
  function serializabilityNotices(): string[] {
    return errorSpy.mock.calls
      .map(([first]) => (typeof first === 'string' ? first : ''))
      .filter((text) => text.includes('non-serializable value was detected'));
  }

  it('requests the tweet collection from the path the thunk names, once', async () => {
    get.mockResolvedValue({ data: [] });

    await makeStore().dispatch(fetchTweets());

    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith(THUNK_REQUEST_PATH);
  });

  it('settles as fulfilled carrying the response data itself as the payload', async () => {
    const responseData = [
      makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT }),
      makeTweet({ tweet_id: SECOND_TWEET_ID, content: SECOND_CONTENT }),
    ];
    get.mockResolvedValue({ data: responseData });

    const action = await makeStore().dispatch(fetchTweets());

    expect(action.type).toBe(`${THUNK_TYPE_PREFIX}/fulfilled`);
    expect(fetchTweets.fulfilled.match(action)).toBe(true);
    /*
     * Identity, not equality. Line 13 returns `response.data` unchanged - it neither copies the array
     * nor maps it nor validates it against the schema - and only an identity assertion distinguishes
     * that from a return path that rebuilt an equal array.
     */
    expect(action.payload).toBe(responseData);
  });

  it('leaves the slice at status "succeeded" holding that same array', async () => {
    const responseData = [makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT })];
    get.mockResolvedValue({ data: responseData });
    const store = makeStore();

    await store.dispatch(fetchTweets());

    expect(store.getState().tweets.status).toBe('succeeded');
    expect(store.getState().tweets.tweets).toBe(responseData);
    expect(store.getState().tweets.error).toBeNull();
  });

  it('holds a tweet Redux itself reports as non-serializable state', async () => {
    /*
     * A divergence, asserted rather than worked around. `tweetSchema` types `timestamp` as `z.date()`,
     * so the tweet the slice stores carries a `Date`; Redux Toolkit's default middleware detects it and
     * names the path. Nothing fails - the value is stored and readable - but the store's contents are
     * not serializable, which matters for persistence, for time-travel debugging and for hydration.
     */
    const responseData = [makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT })];
    get.mockResolvedValue({ data: responseData });
    const store = makeStore();

    await store.dispatch(fetchTweets());

    expect(store.getState().tweets.tweets[0].timestamp).toBeInstanceOf(Date);

    const notices = serializabilityNotices();

    expect(notices.length).toBeGreaterThanOrEqual(1);
    expect(notices.join('\n')).toContain('tweets.tweets.0.timestamp');
  });

  it('is at status "loading" from dispatch until the request settles', async () => {
    let resolveRequest: (response: { data: unknown }) => void = () => undefined;
    get.mockReturnValue(
      new Promise<{ data: unknown }>((resolve) => {
        resolveRequest = resolve;
      }),
    );
    const store = makeStore();

    const settled = store.dispatch(fetchTweets());
    expect(store.getState().tweets.status).toBe('loading');

    resolveRequest({ data: [] });
    await settled;

    expect(store.getState().tweets.status).toBe('succeeded');
  });

  it('rejects with the slice\u2019s own message when the request itself rejects', async () => {
    /*
     * The same rejection every other case in this file reaches by accident, reached deliberately here:
     * `catch` at lines 14-16 discards whatever it caught and substitutes one fixed string, so a network
     * failure and a missing export are indistinguishable to a consumer.
     */
    get.mockRejectedValue(new Error('the collection request failed'));
    const store = makeStore();

    const action = await store.dispatch(fetchTweets());

    expect(action.type).toBe(`${THUNK_TYPE_PREFIX}/rejected`);
    expect(action.payload).toBe(REJECTION_MESSAGE);
    expect(store.getState().tweets.status).toBe('failed');
    expect(store.getState().tweets.error).toBe(REJECTION_MESSAGE);
  });
});

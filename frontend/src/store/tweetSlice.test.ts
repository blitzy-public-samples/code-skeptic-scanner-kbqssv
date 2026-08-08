/**
 * The suite for `./tweetSlice`: its initial state, its two synchronous case reducers, and the three
 * transitions of the `fetchTweets` async thunk.
 *
 * ## The thunk never fulfils
 *
 * `tweetSlice.ts` line 3 imports `{ api }` from `../services/api`, and that module exports only
 * `fetchTweets`, `fetchTweetById` and `generateResponse` - no `api` binding and no default. `api` is
 * therefore `undefined`, line 12's `api.get('/tweets')` raises a `TypeError` on a property access of
 * `undefined`, and the `catch` at line 14 answers with `rejectWithValue('Failed to fetch tweets')`. No
 * request is ever constructed and no socket is ever opened: the failure lands before any transport is
 * involved, so it is not a network error.
 *
 * That shows up twice below. `rejected` is reached by dispatching the real thunk through a real store, which
 * is the only path through lines 11-15. `pending` and `fulfilled` are reached by applying the thunk's own
 * generated action creators to the reducer, because a dispatched thunk settles as `rejected` every time.
 *
 * ## What this file does not do
 *
 * Nothing here mocks a module, substitutes a transport or registers an msw handler. The interception
 * `src/test-utils/setup-jest.ts` starts stays exactly as that module configures it, and its global
 * `afterEach` fails any test whose request escapes to the network. No timer is faked and no clock is read:
 * awaiting the promise a dispatched thunk returns is the whole synchronisation story.
 *
 * Every fixture comes from `makeTweet`, and every store from `makeStore`. Both are built inside the test
 * that uses them: Immer freezes the array handed to `fulfilled`, so a fixture shared at module scope would
 * be frozen for whichever test ran next.
 *
 * @see frontend/src/store/tweetSlice.ts - the module under test.
 * @see frontend/src/test-utils/factories.ts - `makeTweet`, the source of every fixture below.
 * @see frontend/src/test-utils/render.tsx - `makeStore`, the store the thunk is dispatched through, built
 *   from the slice reducers rather than from `src/store/index.ts`.
 * @see frontend/TESTING.md - the suite conventions and the msw contract.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this suite is shaped as it is.
 * @see docs/testing/TRACEABILITY-MATRIX.md - the construct-by-construct mapping for this suite.
 */

import reducer, { addTweet, fetchTweets, updateTweet } from './tweetSlice';
import { makeTweet } from '../test-utils/factories';
import { makeStore } from '../test-utils/render';

/** Derived through `ReturnType` because `tweetSlice.ts` declares `TweetState` locally and never exports it. */
type TweetState = ReturnType<typeof reducer>;

/** The action-type prefix `createAsyncThunk` derives from the string at `tweetSlice.ts` line 9. */
const THUNK_TYPE_PREFIX = 'tweets/fetchTweets';

/**
 * The `requestId` on the action creators applied directly to the reducer below. Redux Toolkit generates a
 * random one per dispatch; the reducer reads neither, since lines 48-58 use only `status` and `payload`.
 */
const REQUEST_ID = 'test-request-id';

/** The message line 15 hands to `rejectWithValue` and line 57 copies into `state.error`. */
const REJECTION_MESSAGE = 'Failed to fetch tweets';

/** The message Redux Toolkit puts on `action.error` for a `rejectWithValue` rejection; not the payload. */
const REJECT_WITH_VALUE_ERROR_MESSAGE = 'Rejected';

/* Distinguishing values for the two seeded tweets and the tweet that replaces one of them. */
const FIRST_TWEET_ID = 'tweet-first';
const SECOND_TWEET_ID = 'tweet-second';
const FIRST_CONTENT = 'The tweet seeded at index 0.';
const SECOND_CONTENT = 'The tweet seeded at index 1.';
const REPLACEMENT_CONTENT = 'The replacement addressed to the tweet seeded at index 1.';

/**
 * A `tweetSlice` state to apply the reducer to, built fresh on every call so no two tests share one.
 *
 * @param overrides - Fields to replace; whatever is omitted takes the value `tweetSlice.ts` lines 26-30
 * declare.
 * @returns A complete slice state.
 */
function sliceStateWith(overrides: Partial<TweetState> = {}): TweetState {
  return { tweets: [], status: 'idle', error: null, ...overrides };
}

/**
 * The two tweets seeded into `updateTweet`'s state and the tweet that addresses the second of them. The
 * replacement carries `SECOND_TWEET_ID`, so it names the element at index 1 and not the one at index 0.
 *
 * @returns Three freshly built tweets, each distinguishable by `content`.
 */
function seededPairAndReplacement() {
  return {
    first: makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT }),
    second: makeTweet({ tweet_id: SECOND_TWEET_ID, content: SECOND_CONTENT }),
    replacement: makeTweet({ tweet_id: SECOND_TWEET_ID, content: REPLACEMENT_CONTENT }),
  };
}

/**
 * Dispatches the real `fetchTweets` thunk through a store of its own and awaits the one action it settles
 * with. This is the only route through `tweetSlice.ts` lines 11-15.
 *
 * @returns The store the thunk ran against, and the action it settled with.
 */
async function dispatchFetchTweets() {
  const store = makeStore();
  const action = await store.dispatch(fetchTweets());

  return { store, action };
}

describe('tweetSlice: initial state', () => {
  it('starts with an empty tweet list, status "idle" and no error', () => {
    // No case reducer and no extra reducer matches this type, so the slice returns its own initialState.
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
    // Line 37 pushes the payload itself rather than a copy of it.
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
    // Built independently and deep-equal to `seeded`, because `makeTweet` is deterministic.
    const unchanged = sliceStateWith({ tweets: [makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT })] });

    const state = reducer(seeded, addTweet(makeTweet({ tweet_id: SECOND_TWEET_ID, content: SECOND_CONTENT })));

    expect(state.tweets).toHaveLength(2);
    expect(seeded).toEqual(unchanged);
    expect(seeded.tweets).toHaveLength(1);
  });
});

describe('tweetSlice: updateTweet', () => {
  /*
   * Line 40 matches on `tweet.id === action.payload.id`. The `Tweet` shape declares no `id` - its
   * identifier is `tweet_id` - so both sides of every comparison are `undefined`, the first element
   * matches, and `findIndex` returns 0 for any payload whatsoever.
   */
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
    // An empty list is the only input for which `findIndex` returns -1, so the line 41 guard fails.
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
      // The real thunk, dispatched and awaited: it settles as rejected without reaching a transport.
      settle: async () => (await dispatchFetchTweets()).store.getState().tweets,
    },
  ])('$actionType leaves the slice at status "$expectedStatus"', async ({ expectedStatus, settle }) => {
    const state = await settle();

    expect(state.status).toBe(expectedStatus);
  });

  it('pending sets status to "loading" and leaves the tweets and the error as they were', () => {
    const seeded = makeTweet({ tweet_id: FIRST_TWEET_ID, content: FIRST_CONTENT });
    const previousError = 'a rejection recorded before this request started';

    // Lines 48-50 assign `status` and nothing else, so a stale error survives a new request.
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
    // Line 53 assigns `action.payload` rather than copying it.
    expect(state.tweets).toBe(payload);
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
  });
});

describe('tweetSlice: fetchTweets dispatched through a real store', () => {
  it('settles as rejected, carrying the message as the action payload rather than as an error message', async () => {
    const { action } = await dispatchFetchTweets();

    expect(action.type).toBe(`${THUNK_TYPE_PREFIX}/rejected`);
    // Line 15 returns `rejectWithValue(...)`, which puts the message on `payload` and leaves
    // `error.message` as Redux Toolkit's own text for that path.
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

    // The action the thunk really produced, applied to a populated state: lines 56-57 assign `status` and
    // `error` and leave the list alone.
    const state = reducer(sliceStateWith({ tweets: [seeded], status: 'loading' }), action);

    expect(state.tweets).toEqual([seeded]);
    expect(state.status).toBe('failed');
    expect(state.error).toBe(REJECTION_MESSAGE);
  });

  it('is at status "loading" from the moment it is dispatched until it settles', async () => {
    const store = makeStore();

    // Redux Toolkit dispatches the pending action synchronously, before the payload creator runs.
    const settled = store.dispatch(fetchTweets());
    expect(store.getState().tweets.status).toBe('loading');

    await settled;

    expect(store.getState().tweets.status).toBe('failed');
  });
});

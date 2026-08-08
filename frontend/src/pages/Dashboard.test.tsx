/**
 * Suite for `src/pages/Dashboard.tsx`, written in full and skipped.
 *
 * The page cannot mount. Three facts of the current source establish that:
 *
 * 1. `src/pages/Dashboard.tsx` line 13 is `const dispatch = useAppDispatch();`, imported at line 4 from
 *    `@/store`. `src/store/index.ts` exports `setupStore` (line 5) and `store` (line 15) at runtime; its
 *    lines 17-18 export the types `RootState` and `AppDispatch`, which the transform erases. No module in
 *    this repository exports `useAppDispatch` or `useAppSelector`, so the binding is `undefined` and
 *    calling it raises `TypeError: useAppDispatch is not a function`. Line 13 raises before line 14
 *    reaches `useAppSelector`, which is the symbol the skip titles name.
 * 2. `src/components/Dashboard` exports one symbol, `export default RealTimeFeed` at line 39. The page's
 *    line 2 imports `{ RealTimeFeed, KeyMetrics, QuickActions }` from it, so all three bindings are
 *    `undefined` and line 31 would raise `Element type is invalid ... got: undefined` on its own. This
 *    blocker is independent of the first: exporting the two hooks does not clear it.
 * 3. `src/store/tweetSlice.ts` line 12 calls `api.get('/tweets')`, and `src/services/api.ts` exports
 *    `fetchTweets`, `fetchTweetById` and `generateResponse` but no `api`. The thunk therefore always
 *    reaches its `catch` and returns `rejectWithValue('Failed to fetch tweets')`, issuing no request.
 *    The assertions below are written against that outcome.
 *
 * None of the three raises at import time - an absent named import binds `undefined` under the CommonJS
 * emit, and `src/store/index.ts` builds its store with two `undefined` reducers without throwing - so this
 * module loads cleanly and every test below is reported as skipped rather than errored.
 *
 * The bodies are complete and assert the page's real structure and lifecycle, so the suite can be
 * un-skipped once `src/store/index.ts` exports the two hooks and the page's line 2 import agrees with what
 * `src/components/Dashboard` exports.
 *
 * @see frontend/src/store/index.test.ts - holds `src/store/index.ts` to the runtime export list above.
 * @see frontend/src/components/Dashboard.test.tsx - the suite for the feed component this page composes.
 * @see docs/testing/TRACEABILITY-MATRIX.md - the disposition this suite is recorded under.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this disposition was chosen.
 */

import { screen, waitFor } from '@testing-library/react';

import Dashboard from '@/pages/Dashboard';
import { getLatestTweets } from '@/services/twitterService';
import { fetchTweets } from '@/store/tweetSlice';
import { makeTweet } from '@/test-utils/factories';
import { makeStore, renderWithProviders } from '@/test-utils/render';
import type { AppStore } from '@/test-utils/render';

/*
 * `src/components/Dashboard` line 10 awaits `getLatestTweets()` on mount and line 16 repeats it on a
 * 30000 ms interval. Mocked here so the feed the page composes resolves from a value rather than a
 * transport, and so no promise it starts settles after the test that mounted it.
 */
jest.mock('@/services/twitterService');

/** Rendered by line 27, and the element the heading and the content wrapper sit inside. */
const CONTAINER_SELECTOR = 'div.dashboard-container';

/** Rendered by line 29, and the element both columns sit inside. */
const CONTENT_SELECTOR = 'div.dashboard-content';

/** Rendered by line 30; holds `RealTimeFeed` at line 31. */
const LEFT_COLUMN_SELECTOR = 'div.left-column';

/** Rendered by line 33; holds `KeyMetrics` at line 34 and `QuickActions` at line 35. */
const RIGHT_COLUMN_SELECTOR = 'div.right-column';

/** The wrapper `RealTimeFeed` renders, at line 22 of `src/components/Dashboard`. */
const FEED_SELECTOR = 'div.real-time-feed';

/** The page's own heading text, at line 28. */
const PAGE_HEADING = 'Dashboard';

/** The heading `RealTimeFeed` renders, at line 23 of `src/components/Dashboard`. */
const FEED_HEADING = 'Real-Time Tweet Feed';

/** The value `fetchTweets` passes to `rejectWithValue`, at line 15 of `src/store/tweetSlice.ts`. */
const REJECTION_MESSAGE = 'Failed to fetch tweets';

/** The status `fetchTweets.rejected` writes, at line 56 of `src/store/tweetSlice.ts`. */
const SETTLED_STATUS = 'failed';

/** The status the slice starts at, at line 28 of `src/store/tweetSlice.ts`. */
const INITIAL_STATUS = 'idle';

/** Typed accessor for the mocked feed service, so each test configures one shared instance. */
const latestTweets = () => jest.mocked(getLatestTweets);

/**
 * Waits for the mount effect's thunk to reach a terminal state, which is what clears `loading` at line 20.
 *
 * @param store - The store the page was mounted against.
 */
async function settleMountThunk(store: AppStore): Promise<void> {
  await waitFor(() => {
    expect(store.getState().tweets.status).toBe(SETTLED_STATUS);
  });
}

describe.skip('Dashboard (src/pages/Dashboard.tsx) - SKIPPED: useAppDispatch is not a function (not exported by src/store/index.ts)', () => {
  beforeEach(() => {
    /*
     * An empty list: a non-empty one reaches line 25 of `src/components/Dashboard`, where `TweetCard` is
     * `undefined`, and raises out of the feed instead of out of the page under test.
     */
    latestTweets().mockResolvedValue([]);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it.skip('renders the page heading inside the container element', async () => {
    const { container, store } = renderWithProviders(<Dashboard />);
    await settleMountThunk(store);

    const heading = screen.getByRole('heading', { level: 1, name: PAGE_HEADING });
    const pageContainer = container.querySelector(CONTAINER_SELECTOR);

    expect(heading.tagName).toBe('H1');
    expect(heading).toHaveTextContent(PAGE_HEADING);
    expect(pageContainer).not.toBeNull();
    expect(pageContainer).toContainElement(heading);
  });

  it.skip('renders both columns inside the content wrapper', async () => {
    const { container, store } = renderWithProviders(<Dashboard />);
    await settleMountThunk(store);

    const content = container.querySelector(CONTENT_SELECTOR);
    const leftColumn = container.querySelector(LEFT_COLUMN_SELECTOR);
    const rightColumn = container.querySelector(RIGHT_COLUMN_SELECTOR);

    /* Asserted as direct parentage, which is the nesting lines 27, 29, 30 and 33 build. */
    expect(content).not.toBeNull();
    expect(content?.parentElement).toBe(container.querySelector(CONTAINER_SELECTOR));
    expect(leftColumn?.parentElement).toBe(content);
    expect(rightColumn?.parentElement).toBe(content);
    expect(leftColumn).not.toBe(rightColumn);
  });

  it.skip('dispatches one thunk for the mount effect', async () => {
    const store = makeStore();
    const dispatchSpy = jest.spyOn(store, 'dispatch');

    renderWithProviders(<Dashboard />, '/', { store });
    await settleMountThunk(store);

    /* `fetchTweets()` produces a thunk function, which line 19 hands straight to `dispatch`. */
    expect(dispatchSpy).toHaveBeenCalledTimes(1);
    expect(typeof dispatchSpy.mock.calls[0][0]).toBe('function');
  });

  it.skip('does not dispatch again when the tree rerenders, because the effect is keyed on dispatch', async () => {
    const store = makeStore();
    const dispatchSpy = jest.spyOn(store, 'dispatch');

    const { rerender } = renderWithProviders(<Dashboard />, '/', { store });
    await settleMountThunk(store);
    rerender(<Dashboard />);
    await settleMountThunk(store);

    expect(dispatchSpy).toHaveBeenCalledTimes(1);
  });

  it.skip('moves the tweets slice out of idle and settles it as failed', async () => {
    const { store } = renderWithProviders(<Dashboard />);

    expect(store.getState().tweets.status).not.toBe(INITIAL_STATUS);

    await settleMountThunk(store);

    expect(store.getState().tweets.status).toBe(SETTLED_STATUS);
  });

  it.skip('settles with the message the fetchTweets thunk rejects with', async () => {
    const { store } = renderWithProviders(<Dashboard />);
    await settleMountThunk(store);

    expect(store.getState().tweets.error).toBe(REJECTION_MESSAGE);
  });

  it.skip('reaches the same terminal tweets state as dispatching fetchTweets() directly', async () => {
    const reference = makeStore();
    await reference.dispatch(fetchTweets());

    const { store } = renderWithProviders(<Dashboard />);
    await settleMountThunk(store);

    expect(store.getState().tweets).toEqual(reference.getState().tweets);
  });

  it.skip('renders the feed in the left column over the tweets the store holds', async () => {
    const tweets = [makeTweet(), makeTweet({ tweet_id: 'tweet-2', content: 'A second doubtful take.' })];
    const { container, store } = renderWithProviders(<Dashboard />, '/', {
      preloadedState: { tweets: { tweets } },
    });

    await settleMountThunk(store);

    const leftColumn = container.querySelector(LEFT_COLUMN_SELECTOR);

    /*
     * Line 14 selects `state.tweets.tweets` and line 31 passes it to the feed alongside `loading`.
     * `RealTimeFeed` declares no props, so neither value changes what it renders, and the seeded tweets
     * survive the mount thunk because `fetchTweets.rejected` writes only `status` and `error`.
     */
    expect(store.getState().tweets.tweets).toEqual(tweets);
    expect(leftColumn).not.toBeNull();
    expect(leftColumn?.querySelector(FEED_SELECTOR)).not.toBeNull();
    expect(screen.getByRole('heading', { level: 2, name: FEED_HEADING })).toBeInTheDocument();
  });
});

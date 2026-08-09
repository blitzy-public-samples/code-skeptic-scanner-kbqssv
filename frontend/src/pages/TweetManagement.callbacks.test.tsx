/**
 * Suite over `frontend/src/pages/TweetManagement.tsx`'s three callbacks and its selected-tweet block.
 *
 * Separate from `./TweetManagement.test.tsx` because the two need different children, and `jest.mock`
 * governs a whole module. That file mounts the **real** `TweetList`, which is how the page behaves in
 * the application; this one substitutes it, because the real child never calls any of the page's
 * callbacks - it declares one prop, `filters`, and offers no way to report a selection, a filter change
 * or a sort change - so `handleTweetSelect` (L15-23), `handleFilterChange` (L25-27),
 * `handleSortChange` (L29-31) and the block at L44-49 are unreachable through it.
 *
 * Only the child is substituted, and its export surface is mirrored exactly: `TweetList` and nothing
 * else, so `TweetCard` and `ResponseGenerator` stay `undefined` here precisely as they are in
 * production. Every other module in the page's graph - the page itself, `@/services/twitterService`,
 * the store - is the real one.
 *
 * @see frontend/src/pages/TweetManagement.test.tsx - the same page over its real child.
 * @see frontend/src/components/TweetManagement.test.tsx - the child's own suite.
 */

import { act, cleanup } from '@testing-library/react';

import TweetManagement from './TweetManagement';
import * as twitterService from '../services/twitterService';
import { renderWithProviders } from '../test-utils/render';

/** Props the page passes to its child, in the order the child received them. */
const mockChildProps: Record<string, unknown>[] = [];

/** `data-testid` the substituted child renders under. */
const CHILD_TESTID = 'tweet-list-child';

jest.mock('@/components/TweetManagement', () => ({
  TweetList: (props: Record<string, unknown>) => {
    mockChildProps.push(props);
    return require('react').createElement('div', { 'data-testid': 'tweet-list-child' });
  },
}));

/** Id handed to the page's `onTweetSelect`. */
const SELECTED_TWEET_ID = 'tweet-selected-7';

/** First argument of the page's line-20 `console.error`, a literal in its source. */
const DETAILS_ERROR_MARKER = 'Error fetching tweet details:';

/** Message of the rejection the details lookup is driven with. */
const DETAILS_FAILURE_MESSAGE = 'the tweet details could not be read';

/** How React reports an element built from a binding that resolved to `undefined`. */
const INVALID_ELEMENT_TYPE = /Element type is invalid/;

describe('pages/TweetManagement with its child substituted', () => {
  let errorSpy: jest.SpyInstance;
  let getTweetDetails: jest.SpyInstance;

  beforeEach(() => {
    mockChildProps.length = 0;
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    /*
     * Spied rather than replaced: `getTweetDetails` is a real export of
     * `@/services/twitterService`, and the page reads it off that namespace at call time.
     */
    getTweetDetails = jest.spyOn(twitterService, 'getTweetDetails');
  });

  afterEach(() => {
    getTweetDetails.mockRestore();
    errorSpy.mockRestore();
  });

  /** The most recent props the child was rendered with. */
  function latestChildProps(): Record<string, unknown> {
    expect(mockChildProps.length).toBeGreaterThanOrEqual(1);
    return mockChildProps[mockChildProps.length - 1];
  }

  it('hands the child its initial filters, sort option and three callbacks', () => {
    renderWithProviders(<TweetManagement />);

    const props = latestChildProps();

    /* Lines 12-13: the two initialisers, and lines 38-42 forward them under these names. */
    expect(props.filters).toEqual({});
    expect(props.sortOption).toBe('');
    expect(typeof props.onTweetSelect).toBe('function');
    expect(typeof props.onFilterChange).toBe('function');
    expect(typeof props.onSortChange).toBe('function');
    /* Those five and nothing else. */
    expect(Object.keys(props).sort()).toEqual([
      'filters',
      'onFilterChange',
      'onSortChange',
      'onTweetSelect',
      'sortOption',
    ]);
  });

  it('forwards a filter change straight back down to the child', () => {
    renderWithProviders(<TweetManagement />);
    const replacement = { hasMedia: true, minDoubtRating: 0.7 };

    act(() => {
      (latestChildProps().onFilterChange as (next: unknown) => void)(replacement);
    });

    /* Line 26 stores the object it was given, and line 38 passes that same object down. */
    expect(latestChildProps().filters).toBe(replacement);
  });

  it('forwards a sort-option change straight back down to the child', () => {
    renderWithProviders(<TweetManagement />);

    act(() => {
      (latestChildProps().onSortChange as (next: string) => void)('doubt_rating');
    });

    expect(latestChildProps().sortOption).toBe('doubt_rating');
  });

  it('looks the selected tweet up through getTweetDetails, by id, once', async () => {
    /* Resolves with `null`, so line 18 stores a falsy value and the block at 44-49 stays guarded. */
    getTweetDetails.mockResolvedValue(null);
    renderWithProviders(<TweetManagement />);

    await act(async () => {
      await (latestChildProps().onTweetSelect as (id: string) => Promise<void>)(
        SELECTED_TWEET_ID,
      );
    });

    expect(getTweetDetails).toHaveBeenCalledTimes(1);
    expect(getTweetDetails).toHaveBeenCalledWith(SELECTED_TWEET_ID);
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('renders no selected-tweet block while the lookup yields nothing', async () => {
    getTweetDetails.mockResolvedValue(null);
    const { container } = renderWithProviders(<TweetManagement />);

    await act(async () => {
      await (latestChildProps().onTweetSelect as (id: string) => Promise<void>)(
        SELECTED_TWEET_ID,
      );
    });

    expect(container.querySelector('.tweet-management__selected-tweet')).toBeNull();
    expect(container.querySelector(`[data-testid="${CHILD_TESTID}"]`)).toBeInTheDocument();
  });

  it('fails on the undefined TweetCard once a tweet is actually selected', async () => {
    /*
     * The ceiling this page carries, reached for the first time here. A resolved lookup makes
     * `selectedTweet` truthy, so lines 44-49 build elements from `TweetCard` and `ResponseGenerator` -
     * two names line 2 imports and `@/components/TweetManagement` does not export. React refuses the
     * first of them and tears the tree down. Asserted as current behaviour: supplying the components
     * would be implementing a missing product feature.
     */
    getTweetDetails.mockResolvedValue({ id: SELECTED_TWEET_ID, text: 'a selected tweet' });
    renderWithProviders(<TweetManagement />);
    const select = latestChildProps().onTweetSelect as (id: string) => Promise<void>;

    let raised: unknown;
    try {
      await act(async () => {
        await select(SELECTED_TWEET_ID);
      });
    } catch (error: unknown) {
      raised = error;
    } finally {
      /*
       * Unmounted here rather than by the automatic teardown. React leaves a root whose render threw in
       * an errored state, and the automatic cleanup of one is unreliable enough to make the *next* test
       * in this file render nothing - which was observed before this line existed. Tearing the root down
       * inside the test that broke it keeps the suite order-independent.
       */
      cleanup();
    }

    /*
     * The thrown error is the oracle here, not React's console output: on a failed *update* React
     * rethrows through `act` rather than writing the attribution record it writes for a failed initial
     * mount, and which of the two it does is a framework detail rather than this page's contract.
     */
    expect(raised).toBeInstanceOf(Error);
    expect((raised as Error).message).toMatch(INVALID_ELEMENT_TYPE);
    expect((raised as Error).message).toMatch(/got: undefined/);
    /* The lookup itself succeeded, so the failure is the render rather than the fetch. */
    expect(getTweetDetails).toHaveBeenCalledTimes(1);
    expect(errorSpy.mock.calls.filter(([marker]) => marker === DETAILS_ERROR_MARKER)).toEqual([]);
  });

  it('swallows a failed lookup, logging it and leaving the page mounted', async () => {
    const failure = new Error(DETAILS_FAILURE_MESSAGE);
    getTweetDetails.mockRejectedValue(failure);
    const { container } = renderWithProviders(<TweetManagement />);

    await act(async () => {
      await (latestChildProps().onTweetSelect as (id: string) => Promise<void>)(
        SELECTED_TWEET_ID,
      );
    });

    /* Lines 19-22 catch it and report it; nothing rethrows, so the page survives. */
    expect(errorSpy).toHaveBeenCalledWith(DETAILS_ERROR_MARKER, failure);
    expect(container.querySelector('div.tweet-management')).toBeInTheDocument();
    /* `selectedTweet` was never assigned, so the block at 44-49 is still guarded out. */
    expect(container.querySelector('.tweet-management__selected-tweet')).toBeNull();
  });
});

/**
 * Colocated suite for `frontend/src/components/TweetManagement`, an extension-less module whose only
 * export is `TweetList` - a named export, with no default export, that requires a `filters` prop.
 *
 * Three properties of that module shape every case below.
 *
 * 1. It imports `getTweets` from `@/services/twitterService`. That module exports `getLatestTweets`
 *    and `getTweetDetails` and nothing else, so `getTweets` is `undefined` and the mount-time
 *    `await getTweets(filters, page)` throws a `TypeError` before any transport is reached. Under
 *    this suite's CommonJS emit its message is
 *    `(0 , twitterService_1.getTweets) is not a function`.
 * 2. It imports `TweetCard` from itself. No module in the repository defines or exports that symbol,
 *    so every element the list builds for a tweet has an `undefined` type.
 * 3. `fetchTweets` catches whatever the call throws, records it as
 *    `console.error('Error fetching tweets:', error)` and clears `loading` in `finally`. The failure
 *    is swallowed rather than propagated: the component stays mounted and its markup settles at
 *    `<div class="tweet-list"></div>`.
 *
 * `handleScroll` calls `setPage` only while
 * `window.innerHeight + document.documentElement.scrollTop === document.documentElement.offsetHeight`.
 * jsdom runs no layout engine, so `innerHeight` is 768 while both document measurements are 0 and
 * that equality does not hold until a test makes it hold.
 *
 * @see frontend/TESTING.md - adding a colocated component suite, and the pitfalls this module's
 *   shape creates.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this suite is built as it is.
 */

import { act, waitFor } from '@testing-library/react';

import { TweetList } from '@/components/TweetManagement';
import { makeFeedTweet } from '@/test-utils/factories';
import { renderWithProviders } from '@/test-utils/render';

/*
 * `@/services/twitterService` is replaced by a spread of its own exports: the same two functions on a
 * plain object whose properties are writable. `getTweets` is absent from the spread exactly as it is
 * absent from the module, so the component's call to it throws in every case that does not attach
 * one; the compiled component reads `twitterService_1.getTweets` at call time, so a property attached
 * for one case is what that render calls.
 */
jest.mock('@/services/twitterService', () => ({
  ...jest.requireActual('@/services/twitterService'),
}));

/*
 * The mocked module object itself, which is the object the compiled component reads `getTweets` from.
 * `require` hands back that object. The spread above drops the non-enumerable `__esModule` flag, and
 * the interop helper a namespace import compiles to copies a module object that lacks that flag, so
 * `import * as` would name a copy no render ever reads.
 */
// eslint-disable-next-line @typescript-eslint/no-var-requires
const twitterService = require('@/services/twitterService') as { getTweets?: jest.Mock };

/**
 * The `filters` prop, one object for the whole file. The component's fetch effect depends on
 * `[filters, page]`, so a fresh literal per render would present a new identity on every render and
 * refetch without end; this object's identity never changes, and a mount produces exactly one fetch.
 */
const filters = {};

/** The page `handleScroll` has not yet advanced past, and the second argument of the mount fetch. */
const FIRST_PAGE = 1;

/**
 * Makes the document exactly as tall as the viewport is deep, which is the equality `handleScroll`
 * tests and, in a browser, the moment the reader reaches the bottom of the page. Written as a
 * configurable own property so {@link releaseDocumentBottom} can remove it.
 */
function holdDocumentAtBottom(): void {
  Object.defineProperty(document.documentElement, 'offsetHeight', {
    configurable: true,
    value: window.innerHeight + document.documentElement.scrollTop,
  });
}

/**
 * Removes the own property {@link holdDocumentAtBottom} defines, restoring the inherited accessor
 * that reports 0. A no-op when no case defined it, so it is safe to call after every test.
 */
function releaseDocumentBottom(): void {
  delete (document.documentElement as unknown as { offsetHeight?: number }).offsetHeight;
}

describe('TweetList (src/components/TweetManagement)', () => {
  /*
   * The application's own `console.error` at line 35 of the component is this suite's primary
   * observable. `src/test-utils/setup-jest.ts` intercepts no console method and installs no spy of
   * any kind, so both spies below belong to this suite alone and are created and restored per test.
   */
  let errorSpy: jest.SpyInstance;
  let removeEventListenerSpy: jest.SpyInstance;

  beforeEach(() => {
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');
  });

  afterEach(() => {
    releaseDocumentBottom();
    delete twitterService.getTweets;
    removeEventListenerSpy.mockRestore();
    errorSpy.mockRestore();
  });

  /** Every `'scroll'` removal recorded so far, whoever asked for it. */
  function scrollListenerRemovals(): unknown[][] {
    return removeEventListenerSpy.mock.calls.filter(([type]) => type === 'scroll');
  }

  /** Mounts the list and returns once the mount fetch has failed and been recorded. */
  async function mountAfterFirstFetch() {
    const rendered = renderWithProviders(<TweetList filters={filters} />);
    await waitFor(() => expect(errorSpy).toHaveBeenCalledTimes(1));
    return rendered;
  }

  it('renders an empty tweet-list container once the mount fetch has settled', async () => {
    const { container } = await mountAfterFirstFetch();

    const list = container.querySelector('div.tweet-list');

    expect(list).not.toBeNull();
    expect(list).toBeInTheDocument();
    /* No tweet was appended, and `finally` cleared `loading`, so "Loading..." is gone as well. */
    expect(list).toBeEmptyDOMElement();
    expect(list?.textContent).toBe('');
  });

  it('swallows the missing getTweets export and records it once as a TypeError', async () => {
    const { container } = await mountAfterFirstFetch();

    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy.mock.calls[0]).toHaveLength(2);
    expect(errorSpy).toHaveBeenCalledWith('Error fetching tweets:', expect.any(TypeError));

    /*
     * The message is `(0 , twitterService_1.getTweets) is not a function`. `getTweets` is the symbol
     * the component named; the `twitterService_1` qualifier and the parentheses V8 reports the callee
     * inside are both emitted by the transform.
     */
    const recorded = errorSpy.mock.calls[0][1] as TypeError;
    expect(recorded.message).toMatch(/\bgetTweets\)? is not a function/);

    /* Swallowed, not propagated: the render survived the failure. */
    expect(container.querySelector('div.tweet-list')).toBeInTheDocument();
  });

  it('advances the page and refetches when a scroll event arrives at the document bottom', async () => {
    await mountAfterFirstFetch();

    holdDocumentAtBottom();
    await act(async () => {
      window.dispatchEvent(new Event('scroll'));
    });

    /*
     * `page` has no projection in the markup, so the refetch the `[filters, page]` effect performs -
     * and the second failure it records - is what the increment is observed through.
     */
    await waitFor(() => expect(errorSpy).toHaveBeenCalledTimes(2));
    expect(errorSpy).toHaveBeenNthCalledWith(2, 'Error fetching tweets:', expect.any(TypeError));
  });

  it('ignores a scroll event that arrives short of the document bottom', async () => {
    await mountAfterFirstFetch();

    expect(window.innerHeight + document.documentElement.scrollTop).not.toBe(
      document.documentElement.offsetHeight,
    );

    await act(async () => {
      window.dispatchEvent(new Event('scroll'));
    });

    expect(errorSpy).toHaveBeenCalledTimes(1);
  });

  it('removes its scroll listener on unmount and refetches no further', async () => {
    const { unmount } = await mountAfterFirstFetch();

    /* The listener effect has an empty dependency list, so nothing is removed before unmount. */
    expect(scrollListenerRemovals()).toHaveLength(0);

    unmount();

    expect(scrollListenerRemovals()).toHaveLength(1);
    expect(removeEventListenerSpy).toHaveBeenCalledWith('scroll', expect.any(Function));

    holdDocumentAtBottom();
    await act(async () => {
      window.dispatchEvent(new Event('scroll'));
    });

    expect(errorSpy).toHaveBeenCalledTimes(1);
  });

  it('fails on the undefined TweetCard element type once getTweets resolves with a tweet', async () => {
    /*
     * `getTweets` is attached for this case alone and removed in `afterEach`. It is the only way the
     * append at line 33 and the `TweetCard` element at line 60 are reached: no module exports
     * `getTweets`, and none defines `TweetCard`, so in the application both lines are unreachable.
     */
    twitterService.getTweets = jest.fn().mockResolvedValue([makeFeedTweet()]);

    let container: HTMLElement | undefined;
    const mountAndFlush = async (): Promise<void> => {
      await act(async () => {
        container = renderWithProviders(<TweetList filters={filters} />).container;
      });
    };

    /* React rethrows the invalid element type out of the flush rather than only recording it. */
    await expect(mountAndFlush()).rejects.toThrow(
      /Element type is invalid: .+ but got: undefined\./,
    );

    expect(twitterService.getTweets).toHaveBeenCalledTimes(1);
    const [forwardedFilters, forwardedPage] = twitterService.getTweets.mock.calls[0];
    expect(forwardedFilters).toBe(filters);
    expect(forwardedPage).toBe(FIRST_PAGE);

    /* React tears the tree down: the container the list rendered into is left empty. */
    expect(container).toBeDefined();
    expect(container).toBeEmptyDOMElement();
  });
});

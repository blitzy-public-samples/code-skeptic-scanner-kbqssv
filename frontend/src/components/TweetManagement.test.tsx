/**
 * The suite for `TweetList`, the sole named export of `frontend/src/components/TweetManagement`.
 *
 * ## The loading indicator is not announced - a documented ceiling
 *
 * L62 of the subject renders `{loading && <div>Loading...</div>}`. A bare `div` has no implicit ARIA
 * role and the subject adds none, so the indicator's appearance and disappearance are silent: a
 * screen-reader user is told neither that a fetch started nor that it finished, and the container it
 * sits in - `div.tweet-list` - is not a live region either, so the tweets that eventually replace it
 * are not announced. The only signal is visual.
 *
 * `role="status"` (or `aria-live="polite"` plus `aria-busy` on the list) is what would make it
 * audible, and adding either means editing `frontend/src/components/TweetManagement`, which is
 * production code this programme is not authorized to change - the two authorized touches are both
 * in `backend/`. The behaviour is therefore pinned as it stands: the case below asserts the absence
 * of every announcement mechanism, so adding one becomes a deliberate, test-visible change. It is
 * recorded as a ceiling in `frontend/TESTING.md`, `docs/testing/TRACEABILITY-MATRIX.md` §G and the
 * suggested-next-tasks lists.
 *
 * @see frontend/src/components/TweetManagement - the module under test.
 * @see frontend/src/components/Dashboard.test.tsx - the same ceiling on the polled feed.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this is recorded, not fixed.
 */

import { act, waitFor } from '@testing-library/react';

import { TweetList } from '@/components/TweetManagement';
import { makeFeedTweet } from '@/test-utils/factories';
import { renderWithProviders } from '@/test-utils/render';

/* Keep a writable mock namespace so tests can attach the otherwise-missing getTweets export. */
jest.mock('@/services/twitterService', () => ({
  ...jest.requireActual('@/services/twitterService'),
}));

/* Use require to access the exact CommonJS object the compiled component reads at call time. */
const twitterService = require('@/services/twitterService') as { getTweets?: jest.Mock };

/** Reuse one filters object; a new identity on every render would retrigger the effect indefinitely. */
const filters = {};

const FIRST_PAGE = 1;

/** The event type the component's own listener is registered under. */
const SCROLL_EVENT = 'scroll';

/** Text of the element the component renders while a fetch is in flight. */
const LOADING_TEXT = 'Loading...';

/** The container L58 renders, and the element the indicator and every tweet card sit inside. */
const LIST_SELECTOR = 'div.tweet-list';

/**
 * Every attribute that would make the indicator's appearance, or the list's replacement of it,
 * reach assistive technology. The subject sets none of them on either element.
 */
const ANNOUNCEMENT_ATTRIBUTES = ['role', 'aria-live', 'aria-busy', 'aria-atomic', 'aria-relevant'] as const;

/** Roles a screen reader would find an announced loading indicator under. */
const ANNOUNCEMENT_ROLES = ['status', 'alert', 'progressbar', 'log'] as const;

/** Override offsetHeight to satisfy the component's exact bottom-of-page equality. */
function holdDocumentAtBottom(): void {
  Object.defineProperty(document.documentElement, 'offsetHeight', {
    configurable: true,
    value: window.innerHeight + document.documentElement.scrollTop,
  });
}

/** Remove the temporary offsetHeight property after each test. */
function releaseDocumentBottom(): void {
  delete (document.documentElement as unknown as { offsetHeight?: number }).offsetHeight;
}

describe('TweetList (src/components/TweetManagement)', () => {
  let errorSpy: jest.SpyInstance;
  let addEventListenerSpy: jest.SpyInstance;
  let removeEventListenerSpy: jest.SpyInstance;

  beforeEach(() => {
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    /*
     * Both listener spies call through, so registration and removal still take effect on the real
     * `window` and every case that dispatches a `'scroll'` event exercises the real listener set. They
     * record the arguments alone, which is what the cleanup case compares.
     */
    addEventListenerSpy = jest.spyOn(window, 'addEventListener');
    removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');
  });

  afterEach(() => {
    releaseDocumentBottom();
    delete twitterService.getTweets;
    removeEventListenerSpy.mockRestore();
    addEventListenerSpy.mockRestore();
    errorSpy.mockRestore();
  });

  /** Every `'scroll'` registration recorded so far, whoever asked for it. */
  function scrollListenerRegistrations(): unknown[][] {
    return addEventListenerSpy.mock.calls.filter(([type]) => type === SCROLL_EVENT);
  }

  /** Every `'scroll'` removal recorded so far, whoever asked for it. */
  function scrollListenerRemovals(): unknown[][] {
    return removeEventListenerSpy.mock.calls.filter(([type]) => type === SCROLL_EVENT);
  }

  async function mountAfterFirstFetch() {
    const rendered = renderWithProviders(<TweetList filters={filters} />);
    await waitFor(() => expect(errorSpy).toHaveBeenCalledTimes(1));
    return rendered;
  }

  it('renders the loading indicator while a supplied getTweets is still in flight', async () => {
    /*
     * A promise this test holds open. Attaching it is the only way to observe the component
     * mid-fetch: with `getTweets` absent the call throws synchronously and `finally` clears
     * `loading` in the same turn, so the loading state is never on screen long enough to see.
     */
    let resolveFetch: (tweets: unknown[]) => void = () => undefined;
    const inFlight = new Promise<unknown[]>((resolve) => {
      resolveFetch = resolve;
    });

    twitterService.getTweets = jest.fn().mockReturnValue(inFlight);

    const { container, getByText } = renderWithProviders(<TweetList filters={filters} />);

    /* `setLoading(true)` ran before the await, so the indicator is rendered inside the container. */
    expect(getByText(LOADING_TEXT)).toBeInTheDocument();
    expect(container.querySelector('div.tweet-list')?.textContent).toBe(LOADING_TEXT);

    /* Nothing has failed: the default path's log is absent because this call has not settled. */
    expect(errorSpy).not.toHaveBeenCalled();

    await act(async () => {
      resolveFetch([]);
      await inFlight;
    });

    /* `finally` cleared `loading`, so the indicator is gone. */
    expect(container.querySelector('div.tweet-list')?.textContent).toBe('');
  });

  it('announces neither the loading indicator nor its replacement, the indicator being a bare div in a container that is not a live region', async () => {
    let resolveFetch: (tweets: unknown[]) => void = () => undefined;
    const inFlight = new Promise<unknown[]>((resolve) => {
      resolveFetch = resolve;
    });

    twitterService.getTweets = jest.fn().mockReturnValue(inFlight);

    const { container, getByText, queryByRole } = renderWithProviders(
      <TweetList filters={filters} />,
    );

    const indicator = getByText(LOADING_TEXT);
    const list = container.querySelector(LIST_SELECTOR);

    /* A bare `div`, which carries no implicit role. */
    expect(indicator.tagName).toBe('DIV');
    expect(list).not.toBeNull();

    /* Neither the indicator nor the container it sits in declares any announcement mechanism. */
    for (const attribute of ANNOUNCEMENT_ATTRIBUTES) {
      expect(indicator).not.toHaveAttribute(attribute);
      expect(list).not.toHaveAttribute(attribute);
    }

    /* So no role query reaches it: the appearance of the indicator is a visual event only. */
    for (const role of ANNOUNCEMENT_ROLES) {
      expect(queryByRole(role)).toBeNull();
    }

    await act(async () => {
      resolveFetch([]);
      await inFlight;
    });

    /*
     * And its removal is silent too. The container swaps its content with no live region around it,
     * so a screen reader is told neither that the fetch finished nor what replaced the indicator.
     */
    expect(container.querySelector(LIST_SELECTOR)?.textContent).toBe('');
    for (const role of ANNOUNCEMENT_ROLES) {
      expect(queryByRole(role)).toBeNull();
    }
  });

  it('renders an empty container and no error when a supplied getTweets resolves with []', async () => {
    /*
     * The reachable success path. An empty resolution is the only one that survives it: the append
     * at line 33 then produces an empty list, and the `TweetCard` element the map would build for a
     * tweet is undefined, which the last case in this file asserts.
     */
    twitterService.getTweets = jest.fn().mockResolvedValue([]);

    const { container } = renderWithProviders(<TweetList filters={filters} />);

    await waitFor(() => expect(twitterService.getTweets).toHaveBeenCalledTimes(1));

    const list = container.querySelector('div.tweet-list');

    expect(list).toBeInTheDocument();
    expect(list).toBeEmptyDOMElement();

    /* Distinct from the default path, whose identical markup is reached through a logged failure. */
    expect(errorSpy).not.toHaveBeenCalled();

    const [forwardedFilters, forwardedPage] = twitterService.getTweets.mock.calls[0];

    expect(forwardedFilters).toBe(filters);
    expect(forwardedPage).toBe(FIRST_PAGE);
  });

  it('renders an empty tweet-list container once the mount fetch has settled', async () => {
    const { container } = await mountAfterFirstFetch();

    const list = container.querySelector('div.tweet-list');

    expect(list).not.toBeNull();
    expect(list).toBeInTheDocument();
    expect(list).toBeEmptyDOMElement();
    expect(list?.textContent).toBe('');
  });

  it('swallows the missing getTweets export and records it once as a TypeError', async () => {
    const { container } = await mountAfterFirstFetch();

    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy.mock.calls[0]).toHaveLength(2);
    expect(errorSpy).toHaveBeenCalledWith('Error fetching tweets:', expect.any(TypeError));

    const recorded = errorSpy.mock.calls[0][1] as TypeError;
    expect(recorded.message).toMatch(/\bgetTweets\)? is not a function/);

    expect(container.querySelector('div.tweet-list')).toBeInTheDocument();
  });

  it('advances the page and refetches when a scroll event arrives at the document bottom', async () => {
    await mountAfterFirstFetch();

    holdDocumentAtBottom();
    await act(async () => {
      window.dispatchEvent(new Event('scroll'));
    });

    /* page is not rendered, so the refetch/error record is the observable effect of incrementing it. */
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

  it('removes on unmount the very scroll callback it registered, once, with matching options', async () => {
    const { unmount } = await mountAfterFirstFetch();

    /* One registration, from the single mount pass of the listener effect. */
    const registrations = scrollListenerRegistrations();
    expect(registrations).toHaveLength(1);

    /*
     * Registered with two arguments and no third: no capture boolean and no options object. Removal
     * matches a listener on type, callback and capture flag together, so the third argument is part of
     * the identity being compared and its absence on both sides is asserted rather than assumed.
     */
    const [registration] = registrations;
    expect(registration).toHaveLength(2);
    expect(registration[0]).toBe('scroll');
    expect(typeof registration[1]).toBe('function');

    const registeredCallback = registration[1] as EventListener;

    /* The listener effect has an empty dependency list, so nothing is removed before unmount. */
    expect(scrollListenerRemovals()).toHaveLength(0);

    unmount();

    const removals = scrollListenerRemovals();

    expect(removals).toHaveLength(1);

    /*
     * The oracle is object identity, not `expect.any(Function)`. `window.removeEventListener`
     * silently ignores a callback that was never registered, so removing a different function -
     * a fresh closure, or the wrong one of two - would leave the real listener attached and every
     * assertion below would still hold: React discards state updates after unmount without
     * complaint, so the leak has no other visible symptom in this environment.
     */
    expect(removals[0][1]).toBe(registeredCallback);
    expect(removeEventListenerSpy).toHaveBeenCalledWith(SCROLL_EVENT, registeredCallback);

    /*
     * Identity, not shape. `handleScroll` is a fresh function on every render while the effect that
     * registers it has an empty dependency list, so its cleanup closes over the mount pass's copy.
     * `expect.any(Function)` is satisfied by any of those copies, and removal only takes effect for the
     * exact callback that was registered - so the same reference, and a matching argument list, is what
     * establishes that no listener is left behind.
     */
    const [removal] = removals;
    expect(removal[1]).toBe(registeredCallback);
    expect(removal).toHaveLength(registration.length);
    expect(removal[0]).toBe(registration[0]);
    expect(removal[2]).toBe(registration[2]);
    expect(removeEventListenerSpy).toHaveBeenCalledWith('scroll', registeredCallback);

    /*
     * A corollary of the removal rather than a second proof of it: React discards a state update from
     * an unmounted tree, so a leaked listener would also record no further fetch here. It is asserted
     * because a refetch at this point would mean the component kept working after unmount.
     */
    holdDocumentAtBottom();
    await act(async () => {
      window.dispatchEvent(new Event(SCROLL_EVENT));
    });

    expect(errorSpy).toHaveBeenCalledTimes(1);
    /* Unmounting registers nothing new either. */
    expect(scrollListenerRegistrations()).toHaveLength(1);
  });

  it('fails on the undefined TweetCard element type once getTweets resolves with a tweet', async () => {
    /* Attach getTweets only for this case to reach the otherwise-unreachable TweetCard branch. */
    twitterService.getTweets = jest.fn().mockResolvedValue([makeFeedTweet()]);

    let container: HTMLElement | undefined;
    const mountAndFlush = async (): Promise<void> => {
      await act(async () => {
        container = renderWithProviders(<TweetList filters={filters} />).container;
      });
    };

    await expect(mountAndFlush()).rejects.toThrow(
      /Element type is invalid: .+ but got: undefined\./,
    );

    expect(twitterService.getTweets).toHaveBeenCalledTimes(1);
    const [forwardedFilters, forwardedPage] = twitterService.getTweets.mock.calls[0];
    expect(forwardedFilters).toBe(filters);
    expect(forwardedPage).toBe(FIRST_PAGE);

    /*
     * React's own diagnostics, recorded by the spy that keeps them out of the run's output.
     *
     * Three properties are asserted, and deliberately only three: that React reported an invalid
     * element type, that it named `TweetList` as the component responsible, and that it pointed at this
     * module. Those are facts about the product - `TweetCard` is imported by a module that does not
     * export it - and they are what a reader needs in order to act.
     *
     * What is *not* asserted is the layout of React's and jsdom's internal reporting: how many records
     * each writes, how many arguments each record carries, which parts arrive as `console.error` format
     * substitutions rather than interpolated text, and whether jsdom forwards the same error as an
     * object alongside them. `react` and `react-dom` are declared as caret ranges and no lockfile is
     * committed, so a patch release may legitimately reshape all of that while the product behaves
     * identically - and a test that treated the shape as a contract would fail for a reason that has
     * nothing to do with this repository. `renderedText` therefore flattens every record to searchable
     * text and the assertions read it semantically.
     */
    const renderedText = errorSpy.mock.calls
      .map((call) =>
        call
          .map((argument) => {
            if (typeof argument === 'string') {
              return argument;
            }
            if (argument instanceof Error) {
              return argument.message;
            }
            const forwarded = argument as { detail?: unknown } | null;
            if (forwarded?.detail instanceof Error) {
              return forwarded.detail.message;
            }
            return String(argument);
          })
          .join(' '),
      )
      .join('\n');

    /* React reported an invalid element type, and named the value `TweetCard` resolved to. */
    expect(renderedText).toMatch(/type is invalid/);
    expect(renderedText).toMatch(/undefined/);

    /* It attributed the element to the component that built it. */
    expect(renderedText).toContain('Check the render method of `TweetList`.');

    /* And the component stack points into this module rather than somewhere else in the tree. */
    expect(renderedText).toMatch(/components[\\/]TweetManagement:\d+:\d+/);

    /* React tears the tree down: the container the list rendered into is left empty. */
    expect(container).toBeDefined();
    expect(container).toBeEmptyDOMElement();
  });
});

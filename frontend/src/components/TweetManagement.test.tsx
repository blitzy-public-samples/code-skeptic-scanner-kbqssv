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
     * React's own diagnostics, recorded by the spy that keeps them out of the run's output. They are
     * asserted rather than merely silenced: they are the only place the *name* of the invalid element
     * appears, and they are how a change in the way React reports it would be noticed.
     *
     * Two validation records, not one. React re-runs the render synchronously after the throw to build
     * a component stack, and the element is validated again on that pass.
     */
    const records = errorSpy.mock.calls;
    const invalidElementRecords = records.filter(
      (call) => typeof call[0] === 'string' && call[0].includes('React.jsx: type is invalid'),
    );
    expect(invalidElementRecords).toHaveLength(2);
    invalidElementRecords.forEach((call) => {
      /* The format string plus its three substitutions, passed unformatted to `console.error`. */
      expect(call).toHaveLength(4);
      expect(call[0]).toContain('expected a string (for built-in components)');
      expect(call[0]).toContain('but got: %s.%s%s');
      /* The substitution for the element type: the value `TweetCard` resolved to. */
      expect(call[1]).toBe('undefined');
      expect(call[2]).toContain('You likely forgot to export your component');
      /* The component that built the element, named by React itself. */
      expect(call[2]).toContain('Check the render method of `TweetList`.');
      /*
       * The component stack, whose top frame is the module that built the element. Matched by module
       * and position rather than by frame name: coverage instrumentation rewrites the function whose
       * name V8 infers, so the same frame reads `at TweetList` under `npm test` and `at filters` under
       * `npm run test:ci`, while the file and line stay put.
       */
      expect(call[3]).toMatch(/^\s+at \S+ \(.*components[\\/]TweetManagement:\d+:\d+\)/);
    });

    /* The single record React writes once it gives up on the tree, carrying the same stack. */
    const teardownRecords = records.filter(
      (call) => typeof call[0] === 'string' && call[0].includes('The above error occurred'),
    );
    expect(teardownRecords).toHaveLength(1);
    expect(teardownRecords[0]).toHaveLength(1);
    expect(teardownRecords[0][0]).toContain('<Fragment> component:');
    /* Through the rendered container, then into the module that built the element. */
    expect(teardownRecords[0][0]).toContain('at div');
    expect(teardownRecords[0][0]).toMatch(/at \S+ \(.*components[\\/]TweetManagement:\d+:\d+\)/);

    /*
     * jsdom forwarding the same uncaught error through its virtual console - once per render pass - as
     * an object rather than a string.
     */
    const forwardedRecords = records.filter((call) => typeof call[0] === 'object' && call[0] !== null);
    expect(forwardedRecords).toHaveLength(2);
    forwardedRecords.forEach((call) => {
      expect(call).toHaveLength(1);
      const forwarded = call[0] as { type: unknown; detail: unknown };
      expect(forwarded.type).toBe('unhandled exception');
      expect(forwarded.detail).toBeInstanceOf(Error);
      expect((forwarded.detail as Error).message).toMatch(
        /Element type is invalid: .+ but got: undefined\./,
      );
    });

    /* Those three groups are the whole census, so a fourth kind of record cannot appear unnoticed. */
    expect(records).toHaveLength(
      invalidElementRecords.length + teardownRecords.length + forwardedRecords.length,
    );

    /* React tears the tree down: the container the list rendered into is left empty. */
    expect(container).toBeDefined();
    expect(container).toBeEmptyDOMElement();
  });
});

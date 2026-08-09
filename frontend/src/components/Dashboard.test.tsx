/**
 * The suite for `RealTimeFeed`, the default export of `frontend/src/components/Dashboard`.
 *
 * ## Polled feed updates are not announced - a documented ceiling
 *
 * L22-L27 of the subject render `<div className="real-time-feed">` around an `<h2>` and a map over
 * the fetched collection, and L16 refetches that collection every 30000 ms. The wrapper is a bare
 * `div`: no `role="log"`, no `role="status"`, no `aria-live`, no `aria-atomic`, no `aria-relevant`,
 * and no `aria-busy` while a poll is in flight. A live-updating region that declares none of those
 * is invisible to assistive technology - content arriving on the 30-second poll is inserted silently,
 * so a screen-reader user is never told the feed changed, and there is no loading state to announce
 * either because the subject renders none at all.
 *
 * `role="log"` with `aria-live="polite"` on the wrapper is what would make the updates audible, and
 * adding it means editing `frontend/src/components/Dashboard`, which is production code this
 * programme is not authorized to change - the two authorized touches are both in `backend/`. The
 * behaviour is therefore pinned as it stands: the case below asserts the absence of every
 * announcement mechanism across a mount and a completed poll, so adding one becomes a deliberate,
 * test-visible change. It is recorded as a ceiling in `frontend/TESTING.md`,
 * `docs/testing/TRACEABILITY-MATRIX.md` §G and the suggested-next-tasks lists.
 *
 * @see frontend/src/components/Dashboard - the module under test.
 * @see frontend/src/components/TweetManagement.test.tsx - the same ceiling on the loading indicator.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this is recorded, not fixed.
 */

import { act, cleanup, screen } from '@testing-library/react';

import RealTimeFeed from '@/components/Dashboard';
import { getLatestTweets } from '@/services/twitterService';
import { makeFeedTweet } from '@/test-utils/factories';
import { renderWithProviders } from '@/test-utils/render';

jest.mock('@/services/twitterService');

const POLL_INTERVAL_MS = 30000;

const ONE_TICK_BEFORE_POLL_MS = 29999;

const FEED_HEADING = 'Real-Time Tweet Feed';

const WRAPPER_SELECTOR = 'div.real-time-feed';

/**
 * Every attribute that would make an update to the polled feed reach assistive technology. The
 * subject sets none of them on the wrapper, asserted individually so a failure names the one that
 * appeared.
 */
const ANNOUNCEMENT_ATTRIBUTES = [
  'role',
  'aria-live',
  'aria-atomic',
  'aria-relevant',
  'aria-busy',
  'aria-label',
] as const;

/** Roles a screen reader would find an announced live feed under. */
const ANNOUNCEMENT_ROLES = ['log', 'status', 'alert', 'feed', 'progressbar'] as const;

const latestTweets = () => jest.mocked(getLatestTweets);

/** Flush the mount fetch and React state update; propagate render errors. */
async function flushPendingFetch(): Promise<void> {
  await act(async () => {});
}

/** Advance fake timers and flush promises started by polling callbacks. */
async function advanceTimers(milliseconds: number): Promise<void> {
  await act(async () => {
    jest.advanceTimersByTime(milliseconds);
  });
}

/** Error the service is made to reject with; asserted by identity, never by message alone. */
const FETCH_FAILURE = new Error('the tweet feed could not be fetched');

/**
 * A promise that never settles, for the mount fetch of the rejection cases.
 *
 * The mount call at line 14 discards its promise, so a mount fetch that rejected would leave an
 * unhandled rejection behind; one that never settles leaves the subject waiting at line 10 forever,
 * which reaches no state update, holds no timer and is discarded when the tree unmounts.
 */
function neverSettles(): Promise<never[]> {
  return new Promise<never[]>(() => undefined);
}

/** Flatten console.error calls because React splits formatted warnings across arguments and calls. */
function reportedText(spy: jest.SpyInstance): string {
  return spy.mock.calls
    .map((callArguments: unknown[]) =>
      callArguments
        .map((argument) => (argument instanceof Error ? argument.message : String(argument)))
        .join(' '),
    )
    .join('\n');
}

describe('RealTimeFeed (src/components/Dashboard)', () => {
  let setIntervalSpy: jest.SpyInstance;
  let clearIntervalSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.useFakeTimers();

    latestTweets().mockReset().mockResolvedValue([]);

    /* Installed after the fake clock, so they wrap its implementations. */
    setIntervalSpy = jest.spyOn(globalThis, 'setInterval');
    clearIntervalSpy = jest.spyOn(globalThis, 'clearInterval');
  });

  afterEach(() => {
    /* Unmount before restoring timer spies, then restore spies before returning to real timers. */
    cleanup();
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('renders the feed heading inside the wrapper element', async () => {
    const { container } = renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();

    const heading = screen.getByRole('heading', { level: 2, name: FEED_HEADING });
    const wrapper = container.querySelector(WRAPPER_SELECTOR);

    expect(heading).toBeInTheDocument();
    expect(heading.tagName).toBe('H2');
    expect(heading).toHaveTextContent(FEED_HEADING);
    expect(wrapper).not.toBeNull();
    expect(wrapper).toContainElement(heading);
  });

  it('fetches once on mount, passing no arguments', async () => {
    renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();

    expect(getLatestTweets).toHaveBeenCalledTimes(1);
    expect(latestTweets().mock.calls[0]).toEqual([]);
  });

  it('does not refetch at 29999 ms', async () => {
    renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();
    expect(getLatestTweets).toHaveBeenCalledTimes(1);

    await advanceTimers(ONE_TICK_BEFORE_POLL_MS);

    expect(getLatestTweets).toHaveBeenCalledTimes(1);
  });

  it('refetches at exactly 30000 ms', async () => {
    renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();
    expect(getLatestTweets).toHaveBeenCalledTimes(1);

    await advanceTimers(ONE_TICK_BEFORE_POLL_MS);
    await advanceTimers(1);

    expect(getLatestTweets).toHaveBeenCalledTimes(2);
  });

  it('keeps refetching every 30000 ms after the first poll', async () => {
    renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();

    await advanceTimers(POLL_INTERVAL_MS);
    expect(getLatestTweets).toHaveBeenCalledTimes(2);

    await advanceTimers(POLL_INTERVAL_MS);
    expect(getLatestTweets).toHaveBeenCalledTimes(3);
  });

  it('announces nothing when the 30000 ms poll refetches, the feed wrapper declaring no live region', async () => {
    const { container } = renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();

    const wrapper = container.querySelector(WRAPPER_SELECTOR);

    /* A bare `div`, which carries no implicit role. */
    expect(wrapper).not.toBeNull();
    expect(wrapper?.tagName).toBe('DIV');

    for (const attribute of ANNOUNCEMENT_ATTRIBUTES) {
      expect(wrapper).not.toHaveAttribute(attribute);
    }

    for (const role of ANNOUNCEMENT_ROLES) {
      expect(screen.queryByRole(role)).toBeNull();
    }

    /* A completed poll changes nothing about that: the refetch is silent, before and after. */
    await advanceTimers(POLL_INTERVAL_MS);
    expect(getLatestTweets).toHaveBeenCalledTimes(2);

    for (const attribute of ANNOUNCEMENT_ATTRIBUTES) {
      expect(container.querySelector(WRAPPER_SELECTOR)).not.toHaveAttribute(attribute);
    }

    for (const role of ANNOUNCEMENT_ROLES) {
      expect(screen.queryByRole(role)).toBeNull();
    }

    /* The heading is the only thing a screen reader is offered, mounted and after the poll alike. */
    expect(screen.getByRole('heading', { level: 2, name: FEED_HEADING })).toBeInTheDocument();
  });

  it('registers the poll as a single 30000 ms interval', async () => {
    renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();

    expect(setIntervalSpy).toHaveBeenCalledTimes(1);
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), POLL_INTERVAL_MS);
  });

  it('clears the polling interval on unmount', async () => {
    const { unmount } = renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();

    const intervalId = setIntervalSpy.mock.results[0].value;

    /* The shared cleanup unmounts only after this test body has finished. */
    unmount();

    expect(clearIntervalSpy).toHaveBeenCalledWith(intervalId);

    await advanceTimers(POLL_INTERVAL_MS * 2);

    expect(getLatestTweets).toHaveBeenCalledTimes(1);
  });

  it('throws Element type is invalid when a tweet reaches the undefined TweetCard', async () => {
    latestTweets().mockResolvedValue([makeFeedTweet()]);

    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    try {
      renderWithProviders(<RealTimeFeed />);

      const flushed = flushPendingFetch();

      await expect(flushed).rejects.toThrow(/Element type is invalid/);
      await expect(flushed).rejects.toThrow(/got: undefined/);
      await expect(flushed).rejects.toThrow(/Check the render method of `RealTimeFeed`/);

      const reported = reportedText(consoleError);

      expect(reported).toContain('React.jsx: type is invalid');
      expect(reported).toContain('Element type is invalid');
      expect(reported).toContain('undefined');
    } finally {
      consoleError.mockRestore();
    }

    expect(getLatestTweets).toHaveBeenCalledTimes(1);
  });

  describe('when the feed service rejects', () => {
    /**
     * Mounts the subject with a mount fetch that never settles, then arms the next fetch to reject.
     *
     * @returns The render result, plus `poll` - the function line 16 registered with `setInterval`,
     *   which is the same object line 14 called at mount, and `intervalId`, the id line 18 clears.
     */
    function mountWithArmedRejection() {
      latestTweets().mockReset().mockReturnValue(neverSettles());

      const rendered = renderWithProviders(<RealTimeFeed />);

      /* One call, from the mount, and one registration, whose callback is the subject's own. */
      expect(getLatestTweets).toHaveBeenCalledTimes(1);
      expect(setIntervalSpy).toHaveBeenCalledTimes(1);

      const poll = setIntervalSpy.mock.calls[0][0] as () => Promise<void>;
      const intervalId = setIntervalSpy.mock.results[0].value;

      latestTweets().mockReset().mockRejectedValueOnce(FETCH_FAILURE);

      return { ...rendered, poll, intervalId };
    }

    it('propagates the rejection out of its own fetch function, unchanged', async () => {
      const { poll } = mountWithArmedRejection();

      /*
       * The subject holds no `try` and no `.catch`, so the error the service rejected with is the
       * error its own function rejects with - the same object, not a copy and not a replacement.
       * This is the promise line 14 and line 16 both discard, which is what makes the rejection
       * unhandled in production.
       */
      await expect(poll()).rejects.toBe(FETCH_FAILURE);
    });

    it('fetches the same way the mount did, with no arguments', async () => {
      const { poll } = mountWithArmedRejection();

      await expect(poll()).rejects.toBe(FETCH_FAILURE);

      /*
       * Line 16 registers the very function line 14 called, so the argument-less call recorded here
       * is the call the mount makes as well: the disposition asserted above is the disposition of
       * both. `getLatestTweets` declares one `count` parameter and receives none, which is the
       * defect the module docstring records.
       */
      expect(latestTweets().mock.calls).toEqual([[]]);
    });

    it('applies no state update and logs nothing', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);
      const { container, poll } = mountWithArmedRejection();

      await expect(poll()).rejects.toBe(FETCH_FAILURE);

      /*
       * Line 11 is never reached, so the tweet list is untouched and the wrapper still holds only
       * the heading: no tweet is rendered and the invalid `TweetCard` is never reached either.
       */
      const wrapper = container.querySelector(WRAPPER_SELECTOR);
      expect(wrapper).not.toBeNull();
      expect(wrapper?.children).toHaveLength(1);
      expect(screen.getByRole('heading', { level: 2, name: FEED_HEADING })).toBeInTheDocument();

      /* The subject has no error handling at all: nothing is logged and nothing is displayed. */
      expect(reportedText(consoleError)).toBe('');
      expect(screen.queryByText(FETCH_FAILURE.message)).toBeNull();
    });

    it('clears its interval on unmount and stops fetching', async () => {
      const { poll, intervalId, unmount } = mountWithArmedRejection();
      await expect(poll()).rejects.toBe(FETCH_FAILURE);

      unmount();

      expect(clearIntervalSpy).toHaveBeenCalledWith(intervalId);

      /* Two further periods produce no fetch, so the failed feed leaves no timer behind. */
      await advanceTimers(POLL_INTERVAL_MS * 2);

      expect(latestTweets().mock.calls).toHaveLength(1);
    });
  });
});

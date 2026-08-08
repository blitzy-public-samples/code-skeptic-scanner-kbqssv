/**
 * Suite for `RealTimeFeed`, the default export of `frontend/src/components/Dashboard` - a file with
 * no extension, reached through the `moduleNameMapper` entry and the transformer that
 * `frontend/jest.config.js` registers for it.
 *
 * Two properties of the subject shape everything below.
 *
 * 1. Line 10 calls `getLatestTweets()` with **no arguments**, while
 *    `frontend/src/services/twitterService.ts` declares `getLatestTweets(count: number)`, so the
 *    declared `count` arrives as `undefined`.
 * 2. Line 3 imports `TweetCard` from `@/components/TweetManagement`, which exports only `TweetList`
 *    and imports `TweetCard` from itself. `TweetCard` is therefore `undefined`, and it is exported
 *    by nothing anywhere in the repository, so line 25 cannot render a tweet.
 *
 * The mounted tree calls `setInterval` exactly once, so the spy's first recorded result is the
 * subject's own interval id. The mount fetch settles on the microtask queue while the poll is a
 * timer: advancing the fake clock does not settle a promise, and settling a promise does not fire a
 * timer.
 *
 * @see frontend/src/components/Dashboard - the subject.
 * @see frontend/TESTING.md - how to add a colocated suite, and the pitfalls of this one.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this suite is built this way.
 */

import { act, cleanup, screen } from '@testing-library/react';

import RealTimeFeed from '@/components/Dashboard';
import { getLatestTweets } from '@/services/twitterService';
import { makeFeedTweet } from '@/test-utils/factories';
import { renderWithProviders } from '@/test-utils/render';

/* Replaces the one module the subject fetches through. It is the only module this suite mocks. */
jest.mock('@/services/twitterService');

/** The `setInterval` delay at line 16 of the subject. */
const POLL_INTERVAL_MS = 30000;

/** One millisecond short of {@link POLL_INTERVAL_MS}. */
const ONE_TICK_BEFORE_POLL_MS = 29999;

/** Text of the `h2` at line 23 of the subject. */
const FEED_HEADING = 'Real-Time Tweet Feed';

/** Class on the wrapper `div` at line 22. The element carries no test id, so the class is the handle. */
const WRAPPER_SELECTOR = 'div.real-time-feed';

/** The mocked service function, typed as a mock. */
const latestTweets = () => jest.mocked(getLatestTweets);

/**
 * Settles the promise the mount effect starts at line 14, and lets React apply the `setTweets` that
 * follows it. Rejects with whatever React threw while applying that update.
 */
async function flushPendingFetch(): Promise<void> {
  await act(async () => {});
}

/**
 * Advances the fake clock and settles whatever the fired timer callbacks started, so an assertion
 * that follows sees both the timer and its promise resolved.
 *
 * @param milliseconds - How far to advance the fake clock.
 */
async function advanceTimers(milliseconds: number): Promise<void> {
  await act(async () => {
    jest.advanceTimersByTime(milliseconds);
  });
}

/**
 * Everything a `console.error` spy recorded, one call per line, every argument stringified. React
 * reports an invalid element type across several arguments and several calls, and interpolates the
 * type through a `%s` format specifier instead of writing it into a single argument.
 *
 * @param spy - A spy installed on `console.error`.
 * @returns The recorded text, joined for substring assertions.
 */
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

    /*
     * An array, not `undefined`: line 11 stores whatever resolves and line 24 calls `.map` on it.
     */
    latestTweets().mockReset().mockResolvedValue([]);

    /* Installed after the fake clock, so they wrap its implementations. */
    setIntervalSpy = jest.spyOn(globalThis, 'setInterval');
    clearIntervalSpy = jest.spyOn(globalThis, 'clearInterval');
  });

  afterEach(() => {
    /*
     * Unmounting happens while the fake clock and both spies are still installed. Restoring a spy
     * writes back the implementation it wrapped, which for these two is the fake clock's, and the
     * clock is uninstalled on the line after.
     */
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

  it('registers the poll as a single 30000 ms interval', async () => {
    renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();

    expect(setIntervalSpy).toHaveBeenCalledTimes(1);
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), POLL_INTERVAL_MS);
  });

  it('clears the polling interval on unmount', async () => {
    const { unmount } = renderWithProviders(<RealTimeFeed />);
    await flushPendingFetch();

    /* The only recorded call is the subject's, so its result is the id line 18 clears. */
    const intervalId = setIntervalSpy.mock.results[0].value;

    /* The shared cleanup unmounts only after this test body has finished. */
    unmount();

    expect(clearIntervalSpy).toHaveBeenCalledWith(intervalId);

    /* The cleared interval no longer fires: two further periods produce no additional fetch. */
    await advanceTimers(POLL_INTERVAL_MS * 2);

    expect(getLatestTweets).toHaveBeenCalledTimes(1);
  });

  it('throws Element type is invalid when a tweet reaches the undefined TweetCard', async () => {
    latestTweets().mockResolvedValue([makeFeedTweet()]);

    /*
     * React writes the invalid type to `console.error` before it throws. Captured for this test
     * only, asserted on below, and restored in `finally`.
     */
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    try {
      /* Line 25 is reached by the re-render that line 11 triggers, so the render itself succeeds. */
      renderWithProviders(<RealTimeFeed />);

      const flushed = flushPendingFetch();

      await expect(flushed).rejects.toThrow(/Element type is invalid/);
      await expect(flushed).rejects.toThrow(/got: undefined/);
      await expect(flushed).rejects.toThrow(/Check the render method of `RealTimeFeed`/);

      /* The element was created before it failed to reconcile, so the type warning is reported too. */
      const reported = reportedText(consoleError);

      expect(reported).toContain('React.jsx: type is invalid');
      expect(reported).toContain('Element type is invalid');
      expect(reported).toContain('undefined');
    } finally {
      consoleError.mockRestore();
    }

    /* The single tweet was fetched once; the failure is in rendering it, not in fetching it. */
    expect(getLatestTweets).toHaveBeenCalledTimes(1);
  });
});

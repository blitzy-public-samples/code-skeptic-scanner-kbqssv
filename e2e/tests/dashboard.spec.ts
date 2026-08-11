/**
 * End-to-end coverage of the harness client route `/`.
 *
 * Subject: `RealTimeFeed`, the default export of `frontend/src/components/Dashboard`,
 * which `e2e/harness/main.tsx` mounts at `/`. That module is an extension-less file;
 * `e2e/vite.harness.config.ts` resolves and transforms it.
 *
 * `test` and `expect` come from `./harness-fixtures`, whose two automatic fixtures do the
 * cross-cutting work: `noEgress` aborts every request addressed off the harness origin and
 * fails the test at teardown for any harness API request no route below claimed, and
 * `browserDiagnostics` attaches the browser's console and page errors and fails the test on
 * any it did not declare. Each test therefore installs its own interception before
 * navigating, declares the failures it expects, and holds no state shared with another test.
 *
 * The mount call at `components/Dashboard` L10 passes no argument, so `services/api.ts` builds the
 * literal `undefined/tweets?page=undefined&limit=undefined` - which is the URL every interception
 * below is anchored to. A non-empty collection reaches `TweetCard` at L24-L26, which no module
 * exports.
 *
 * What that costs is larger than the route. Nothing in the subject, in `harness/main.tsx` or
 * anywhere in `frontend/src` is an error boundary, so the invalid element type unmounts the whole
 * root: the `<main>` landmark the harness renders above `<Routes>` goes too, and `#root` is left
 * empty. React's unmount then runs the L18 cleanup, which clears the 30-second poll L16 installed -
 * and with the component gone nothing reinstalls it, so the route cannot refetch its way back. The
 * third test asserts each of those, reading an in-page timer ledger rather than waiting out a poll
 * boundary.
 *
 * The 30-second `setInterval` at L16 and the `clearInterval` at L18 are otherwise covered by
 * `frontend/src/components/Dashboard.test.tsx` under fake timers, which is where the *interval
 * period* itself is asserted; what this file adds is that the same cleanup is what makes the
 * ceiling terminal.
 *
 * @see e2e/README.md - adding a spec to this directory.
 * @see docs/testing/DECISION-LOG.md - the interception, ceiling and layer-boundary rows for this file.
 */

import path from 'node:path';

import type { Page } from '@playwright/test';

import { expect, HARNESS_ORIGIN, test } from './harness-fixtures';

/* -------------------------------------------------------------------------- */
/* Oracles                                                                    */
/* -------------------------------------------------------------------------- */

/** Client route `e2e/harness/main.tsx` mounts the subject at. Resolved against `use.baseURL`. */
const FEED_ROUTE = '/';

/** Container element `components/Dashboard` L22 renders. */
const FEED_CONTAINER = 'div.real-time-feed';

/** Accessible name of the `<h2>` `components/Dashboard` L23 renders. */
const FEED_HEADING = 'Real-Time Tweet Feed';

/** Heading level of that element. */
const FEED_HEADING_LEVEL = 2;

/**
 * Globs covering the collection request `services/api.ts` L8 builds. The second matches the
 * request the subject actually issues; the first covers the shape a configured base URL would
 * produce, and also matches the document request for the `/tweets` route, which every handler's
 * navigation guard hands back to the harness. Playwright runs a single matching handler per
 * request, so each test below registers one handler function under every glob and records into
 * one array.
 *
 * Both are anchored to {@link HARNESS_ORIGIN}, so each claims only requests addressed to the harness
 * origin. A host-agnostic `'**\/tweets*'` also claims a request addressed to a foreign host that
 * shares the path, and fulfilling it hides that
 * destination drift from the `noEgress` fixture's ledger - a green test over a request that left
 * the harness. Anchored, such a request falls through to that fixture, which aborts and records
 * it. `./isolation.spec.ts` asserts exactly that.
 */
const TWEET_COLLECTION_GLOBS = [
  `${HARNESS_ORIGIN}/tweets*`,
  `${HARNESS_ORIGIN}/undefined/tweets*`,
] as const;

/** Pathname of that request, after the browser resolves its relative URL against the harness origin. */
const TWEET_COLLECTION_PATHNAME = '/undefined/tweets';

/** Value `page` and `limit` each carry, being `String(undefined)`. */
const UNDEFINED_QUERY_VALUE = 'undefined';

/** Two-record collection payload, keyed as `frontend/src/schema/tweetSchema.ts` declares. */
const TWEETS_FIXTURE = path.join(__dirname, '..', 'fixtures', 'tweets.json');

/**
 * React's report for an element type that resolved to `undefined`, as it appears in the error React
 * *throws*.
 *
 * The development-mode warning React logs for the same defect is worded differently - see
 * {@link INVALID_ELEMENT_TYPE_WARNING} - so the two are separate oracles rather than one pattern
 * loose enough to match both.
 */
const INVALID_ELEMENT_TYPE = /Element type is invalid/;

/**
 * The same defect as React logs it before throwing: `Warning: React.jsx: type is invalid ...`.
 *
 * Chrome records this with its `%s` placeholders unsubstituted, because React passes the substitutions
 * as separate console arguments, so a pattern for this record must key on the part before them.
 * Reported once per JSX element the render attempted.
 */
const INVALID_ELEMENT_TYPE_WARNING = /Warning: React\.jsx: type is invalid/;

/**
 * React's warning that the mapped children carry no distinct `key`.
 *
 * A second defect on the same two production lines, and asserted rather than merely tolerated:
 * `components/Dashboard` L25 writes `key={tweet.id}`, and `e2e/fixtures/tweets.json` carries
 * `tweet_id` as `frontend/src/schema/tweetSchema.ts` declares it, so every key in the list is
 * `undefined`. The same absent `id` is what makes `store/tweetSlice.ts` overwrite index 0.
 */
const DUPLICATE_KEY_WARNING = /Each child in a list should have a unique "key" prop/;

/** How React reports an error no boundary caught, naming the component it unmounted from. */
const UNCAUGHT_RENDER_REPORT = /The above error occurred in the <\w+> component/;

/** Value React names in that report, which is what the `TweetCard` specifier resolved to. */
const RESOLVED_ELEMENT_TYPE = /got: undefined/;

/** Component React attributes the invalid element type to. */
const REPORTING_COMPONENT = /Check the render method of `RealTimeFeed`/;

/**
 * Budget for a poll over state a mount fetch has to settle first. Below the 30000 ms
 * `setInterval` at `components/Dashboard` L16, so only the mount request falls inside it.
 */
const SETTLE_TIMEOUT_MS = 10_000;

/**
 * The `<main>` landmark `harness/main.tsx` renders *above* `<Routes>`, so it belongs to the page
 * rather than to any route.
 *
 * That is what makes it the oracle for blast radius: a route element disappearing leaves this
 * standing, and this disappearing means the unmount reached above the route into the root itself.
 */
const PAGE_LANDMARK = 'main';

/** Element `harness/index.html` provides and `harness/main.tsx` mounts the whole tree into. */
const REACT_ROOT = '#root';

/** Interval period `components/Dashboard` L16 installs its poll at. */
const POLL_PERIOD_MS = 30_000;

/**
 * One entry of the in-page timer ledger {@link TIMER_LEDGER_SCRIPT} keeps.
 *
 * `delay` is recorded for a `set` and absent for a `clear`, which is what `setInterval` and
 * `clearInterval` respectively carry.
 */
interface TimerOperation {
  op: 'set' | 'clear';
  id: number;
  delay?: number;
}

/**
 * Records every `setInterval` and `clearInterval` the page performs, in order.
 *
 * Installed as an init script so it is in place before any application module evaluates, and both
 * wrappers delegate to the real implementation, so nothing about the subject's timing changes -
 * this observes, it does not substitute.
 *
 * It exists because the alternative is unusable: proving a 30-second poll is *dead* by waiting for
 * the boundary it would have fired at costs more than this file's whole per-test budget, and a
 * request count that has not grown yet is not the same claim. The ledger settles it mechanically -
 * the interval was installed, then cleared, and no later `set` replaced it.
 */
const TIMER_LEDGER_SCRIPT = `
  window.__timerOperations = [];
  const nativeSetInterval = window.setInterval;
  const nativeClearInterval = window.clearInterval;
  window.setInterval = function (handler, delay, ...rest) {
    const id = nativeSetInterval.call(window, handler, delay, ...rest);
    window.__timerOperations.push({ op: 'set', id, delay });
    return id;
  };
  window.clearInterval = function (id) {
    window.__timerOperations.push({ op: 'clear', id });
    return nativeClearInterval.call(window, id);
  };
`;

/**
 * Reads that ledger.
 *
 * @param page - Page under test.
 * @returns Every recorded operation, oldest first.
 */
function timerOperations(page: Page): Promise<TimerOperation[]> {
  return page.evaluate(() => (window as unknown as {
    __timerOperations: TimerOperation[];
  }).__timerOperations);
}

/**
 * Returns the markup inside {@link REACT_ROOT}, which is empty exactly when React has unmounted
 * the whole tree.
 *
 * @param page - Page under test.
 * @returns The root's inner markup.
 */
function reactRootMarkup(page: Page): Promise<string> {
  return page.locator(REACT_ROOT).evaluate((element: Element) => element.innerHTML);
}

test.describe('harness route / - RealTimeFeed (frontend/src/components/Dashboard)', () => {
  test('renders the Real-Time Tweet Feed heading inside the feed container', async ({ page }) => {
    const interceptedUrls: string[] = [];

    // No `browserDiagnostics.allow(...)` here, and that is an assertion: an empty collection reaches
    // no `TweetCard`, so this route must reach the end of the test with a clean console.

    for (const glob of TWEET_COLLECTION_GLOBS) {
      await page.route(glob, async (route) => {
        if (route.request().isNavigationRequest()) {
          await route.continue();
          return;
        }

        interceptedUrls.push(route.request().url());
        await route.fulfill({ json: [] });
      });
    }

    await page.goto(FEED_ROUTE);

    try {
      const container = page.locator(FEED_CONTAINER);
      await expect(container).toBeVisible();

      await expect(
        container.getByRole('heading', { level: FEED_HEADING_LEVEL, name: FEED_HEADING, exact: true }),
      ).toBeVisible();

      await expect(container.locator('*')).toHaveCount(1);
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
    }
  });

  test('requests the tweet collection once per mount from the literal undefined base URL', async ({
    page,
  }) => {
    const interceptedUrls: string[] = [];

    // Nothing declared: this route answers an empty collection, so it must stay error-free too.

    for (const glob of TWEET_COLLECTION_GLOBS) {
      await page.route(glob, async (route) => {
        if (route.request().isNavigationRequest()) {
          await route.continue();
          return;
        }

        interceptedUrls.push(route.request().url());
        await route.fulfill({ json: [] });
      });
    }

    await page.goto(FEED_ROUTE);

    try {
      // One mount, one fetch: `harness/main.tsx` mounts the subject outside `React.StrictMode`.
      await expect
        .poll(() => interceptedUrls.length, {
          message: `expected exactly one ${TWEET_COLLECTION_PATHNAME} request, recorded ${JSON.stringify(interceptedUrls)}`,
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toBe(1);

      const requested = new URL(interceptedUrls[0]);

      // A relative URL, so the browser resolved it against the harness origin.
      expect(requested.origin).toBe(HARNESS_ORIGIN);
      expect(requested.pathname).toBe(TWEET_COLLECTION_PATHNAME);
      expect(requested.searchParams.get('page')).toBe(UNDEFINED_QUERY_VALUE);
      expect(requested.searchParams.get('limit')).toBe(UNDEFINED_QUERY_VALUE);
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
    }
  });

  test('does not render tweet cards because TweetCard is exported by nothing', async ({
    page,
    browserDiagnostics,
  }) => {
    const interceptedUrls: string[] = [];

    /*
     * Here the browser errors *are* the subject, so each is declared rather than tolerated silently.
     * React reports this defect three ways - a warning per attempted element, the uncaught error that
     * tears the route down, and its own report of that unmount - and the absent `key` is a second
     * defect the same two lines produce. Every pattern is keyed on message text rather than on the
     * record's kind, so an unrelated uncaught error in this test still fails it.
     */
    browserDiagnostics.allow(
      INVALID_ELEMENT_TYPE_WARNING,
      INVALID_ELEMENT_TYPE,
      DUPLICATE_KEY_WARNING,
      UNCAUGHT_RENDER_REPORT,
    );

    // Installed before any module evaluates, so the poll L16 installs is recorded from the start.
    await page.addInitScript(TIMER_LEDGER_SCRIPT);

    // A non-empty collection drives the map at L24-L26 into the undefined `TweetCard`.
    for (const glob of TWEET_COLLECTION_GLOBS) {
      await page.route(glob, async (route) => {
        if (route.request().isNavigationRequest()) {
          await route.continue();
          return;
        }

        interceptedUrls.push(route.request().url());
        await route.fulfill({ path: TWEETS_FIXTURE, contentType: 'application/json' });
      });
    }

    await page.goto(FEED_ROUTE);

    try {
      await expect
        .poll(() => browserDiagnostics.errorText(), {
          message: 'expected React to report an invalid element type for the undefined TweetCard',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toMatch(INVALID_ELEMENT_TYPE);

      const reported = browserDiagnostics.text();
      expect(reported).toMatch(RESOLVED_ELEMENT_TYPE);
      expect(reported).toMatch(REPORTING_COMPONENT);

      // It also reached the page as an uncaught error rather than being swallowed, and React
      // reported the unmount that followed.
      expect(browserDiagnostics.pageErrorText()).toMatch(INVALID_ELEMENT_TYPE);
      expect(reported).toMatch(UNCAUGHT_RENDER_REPORT);

      // Every mapped child carried the same `undefined` key, L25 having read a member the fixture
      // shape does not declare.
      expect(reported).toMatch(DUPLICATE_KEY_WARNING);

      await expect(page.locator(FEED_CONTAINER)).toHaveCount(0);

      /*
       * And it took more than the route. `harness/main.tsx` renders the `<main>` landmark and the
       * `<Routes>` element *above* every route element, and nothing anywhere is an error boundary,
       * so the throw unmounts the whole root: the landmark goes with the feed and `#root` is left
       * empty. Asserted because the blast radius is the finding - a reader told only that "the route
       * came down" will expect the rest of the page to have survived, and none of it does.
       */
      await expect(page.locator(PAGE_LANDMARK)).toHaveCount(0);
      expect(await reactRootMarkup(page)).toBe('');

      /*
       * The poll died with it, and permanently. React's unmount runs the L18 cleanup, so the 30 s
       * interval L16 installed is cleared - and because the component is gone, nothing reinstalls
       * it. The route therefore cannot recover on its own: the very mechanism that would have
       * refetched is what the teardown removed.
       *
       * Read from the ledger rather than from a wall-clock wait, so the claim is "the interval was
       * cleared and not replaced" rather than "no request had arrived yet".
       */
      const operations = await timerOperations(page);
      const installedPolls = operations.filter(
        (operation) => operation.op === 'set' && operation.delay === POLL_PERIOD_MS,
      );
      const clears = operations.filter((operation) => operation.op === 'clear');

      expect(installedPolls.length).toBeGreaterThan(0);
      expect(clears).toHaveLength(1);
      expect(installedPolls.map((operation) => operation.id)).toContain(clears[0].id);

      // Nothing was installed after that clear, so no replacement poll exists.
      const afterTheClear = operations.slice(operations.indexOf(clears[0]) + 1);
      expect(afterTheClear.filter((operation) => operation.op === 'set')).toEqual([]);

      // One request, and no second one, consistent with a poll that no longer exists.
      expect(interceptedUrls).toHaveLength(1);
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
    }
  });
});

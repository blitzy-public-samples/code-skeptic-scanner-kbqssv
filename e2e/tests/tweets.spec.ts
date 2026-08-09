/**
 * End-to-end coverage of the harness client route `/tweets`.
 *
 * Subject: `TweetList`, the named export of `frontend/src/components/TweetManagement`,
 * which `e2e/harness/main.tsx` mounts at `/tweets` with a module-scope `filters` object.
 * That module is an extension-less file; `e2e/vite.harness.config.ts` resolves and
 * transforms it, and appends the two names it imports that no module declares - `getTweets`
 * from `services/twitterService` and `TweetCard` from itself - each carrying `undefined`.
 *
 * `test` and `expect` come from `./harness-fixtures`, whose two automatic fixtures do the
 * cross-cutting work: `noEgress` aborts every request addressed off the harness origin and
 * fails the test at teardown for any harness API request no route below claimed, and
 * `browserDiagnostics` attaches the browser's console and page errors and fails the test on
 * any it did not declare. Every test on this route declares {@link FETCH_FAILURE_PREFIX},
 * because the mount fetch fails on every one of them; nothing else is tolerated. Each test
 * installs its own interception before navigating, and holds no state shared with another.
 *
 * The mount call at `components/TweetManagement` L32 throws on an import carrying `undefined`
 * before `services/api.ts` reaches axios, so no collection request is ever issued and L34-L36
 * catch it and report it through `console.error`. The L58 container therefore renders with no
 * child, and so with no bounding box.
 *
 * Rendering the `undefined` `TweetCard` needs a non-empty collection to reach the map at
 * L59-L61, which that throw makes unreachable from this route; that ceiling is covered by
 * `frontend/src/components/TweetManagement.test.tsx`.
 *
 * @see e2e/README.md - adding a spec to this directory.
 * @see docs/testing/DECISION-LOG.md - the interception, ceiling and layer-boundary rows for this file.
 */

import {
  type BrowserDiagnostics,
  expect,
  HARNESS_ORIGIN,
  test,
  unInterceptedApiRequestUrls,
} from './harness-fixtures';

/* -------------------------------------------------------------------------- */
/* Oracles                                                                    */
/* -------------------------------------------------------------------------- */

/** Client route the harness mounts the subject at. Resolved against `use.baseURL`. */
const TWEET_LIST_ROUTE = '/tweets';

/** Container element `components/TweetManagement` L58 renders. */
const TWEET_LIST_CONTAINER = 'div.tweet-list';

/**
 * Globs covering the collection request `services/api.ts` L8 builds. Playwright runs a single
 * matching handler per request, so no test below asserts which glob fired. The document request
 * for {@link TWEET_LIST_ROUTE} also matches the first of them, which is what every handler's
 * navigation guard hands back to the harness.
 *
 * Both are anchored to {@link HARNESS_ORIGIN}, so each claims only requests addressed to the harness
 * origin. A host-agnostic `'**\/tweets*'` also claims a request addressed to a foreign host that
 * shares the path, and fulfilling it hides that
 * destination drift from the `noEgress` fixture's ledger. Anchored, such a request falls through
 * to that fixture, which aborts and records it. `./isolation.spec.ts` asserts exactly that.
 */
const TWEET_COLLECTION_GLOBS = [
  `${HARNESS_ORIGIN}/tweets*`,
  `${HARNESS_ORIGIN}/undefined/tweets*`,
] as const;

/** Prefix `components/TweetManagement` L35 passes to `console.error`. */
const FETCH_FAILURE_PREFIX = 'Error fetching tweets:';

/**
 * {@link FETCH_FAILURE_PREFIX} as an allow-list pattern.
 *
 * Every test on this route declares it, because L32 throws on every mount here, and declaring it
 * makes the absence of any *other* browser error part of each test's verdict.
 */
const EXPECTED_FETCH_FAILURE = /console\.error: Error fetching tweets:/;

/** How a browser reports the call at L32 against an import that carries `undefined`. */
const UNCALLABLE_IMPORT = /is not a function/;

/** The name L2 imports, which `services/twitterService` does not declare. */
const MISSING_EXPORT_NAME = /getTweets/;

/** Budget for a poll over state the mount effect at L25-L27 has to settle first. */
const SETTLE_TIMEOUT_MS = 10_000;

/**
 * Console errors the mount fetch reported, read out of the fixture's ledger.
 *
 * Filtering on {@link FETCH_FAILURE_PREFIX} rather than counting every console error keeps the
 * "exactly one report per mount" assertions honest without making them a census of everything the
 * dev server and React also say - which is what the fixture's own allow-list is for.
 *
 * @param diagnostics - The test's `browserDiagnostics` handle.
 * @returns Each matching record's text, oldest first.
 */
function reportedFetchFailures(diagnostics: BrowserDiagnostics): readonly string[] {
  return diagnostics
    .records()
    .filter((record) => record.failing && record.text.includes(FETCH_FAILURE_PREFIX))
    .map((record) => record.text);
}

test.describe('harness route /tweets - TweetList (frontend/src/components/TweetManagement)', () => {
  test('renders an empty tweet-list container', async ({ page, browserDiagnostics }) => {
    const interceptedUrls: string[] = [];

    // The one failure this route always produces. Anything else the browser reports fails the test.
    browserDiagnostics.allow(EXPECTED_FETCH_FAILURE);

    // Installed before navigating. The guard hands the document request for this route back
    // to the harness.
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

    await page.goto(TWEET_LIST_ROUTE);

    try {
      const container = page.locator(TWEET_LIST_CONTAINER);

      await expect(container).toBeAttached();
      await expect(container).toBeEmpty();
      expect(await container.textContent()).toBe('');

      // No `TweetCard` from the map at L59-L61, and no loading node from L62.
      await expect(container.locator('*')).toHaveCount(0);
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
    }
  });

  test('logs the fetch failure because twitterService declares no getTweets export', async ({
    page,
    browserDiagnostics,
  }) => {
    const interceptedUrls: string[] = [];

    browserDiagnostics.allow(EXPECTED_FETCH_FAILURE);

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

    await page.goto(TWEET_LIST_ROUTE);

    try {
      // One mount, one report: `harness/main.tsx` mounts the subject outside `React.StrictMode`
      // and passes it a module-scope `filters`, so the effect at L25-L27 runs once.
      await expect
        .poll(() => reportedFetchFailures(browserDiagnostics).length, {
          message: `expected exactly one console error carrying "${FETCH_FAILURE_PREFIX}"`,
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toBe(1);

      const [reported] = reportedFetchFailures(browserDiagnostics);

      expect(reported).toMatch(UNCALLABLE_IMPORT);
      expect(reported).toMatch(MISSING_EXPORT_NAME);

      // L34-L36 swallowed it: nothing reached the page as an uncaught error, and the route
      // stayed mounted.
      expect(browserDiagnostics.pageErrorText()).toBe('');
      await expect(page.locator(TWEET_LIST_CONTAINER)).toBeAttached();
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
    }
  });

  test('issues no tweet collection request because the uncallable import throws before axios', async ({
    page,
    browserDiagnostics,
  }) => {
    const interceptedUrls: string[] = [];

    browserDiagnostics.allow(EXPECTED_FETCH_FAILURE);

    // The same handler shape `dashboard.spec.ts` records one request through on `/`.
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

    await page.goto(TWEET_LIST_ROUTE);

    try {
      await expect(page.locator(TWEET_LIST_CONTAINER)).toBeAttached();

      // Reporting the failure is the last statement of the mount fetch's `catch`.
      await expect
        .poll(() => reportedFetchFailures(browserDiagnostics).length, {
          message: `expected the mount fetch to report "${FETCH_FAILURE_PREFIX}" before its ledgers are read`,
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toBe(1);

      // Nothing reached a handler above, and nothing reached the dev server past them either.
      expect(interceptedUrls).toEqual([]);
      expect(unInterceptedApiRequestUrls()).toEqual([]);
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
    }
  });
});

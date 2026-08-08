/**
 * End-to-end coverage of the harness client route `/tweets`.
 *
 * Subject: `TweetList`, the named export of `frontend/src/components/TweetManagement`,
 * which `e2e/harness/main.tsx` L71 mounts at `/tweets` with a module-scope `filters`
 * object. That module is an extension-less file; `e2e/vite.harness.config.ts` resolves and
 * transforms it, and appends the two names it imports that no module declares - `getTweets`
 * from `services/twitterService` and `TweetCard` from itself - each carrying `undefined`.
 *
 * `test` and `expect` come from `./harness-fixtures`, whose automatic `noEgress` fixture
 * aborts every request addressed off the harness origin and fails the test at teardown for
 * any harness API request no route below claimed. Each test therefore installs its own
 * interception before navigating, and holds no state shared with another test.
 *
 * What each test asserts, and the production lines it reads from:
 *
 * | Test | Behaviour asserted |
 * |------|--------------------|
 * | 1 | `components/TweetManagement` L58 renders `div.tweet-list`, and neither the map at L59-L61 nor the loading node at L62 puts anything inside it |
 * | 2 | `components/TweetManagement` L34-L36 catch the call at L32 and report it through `console.error`, rather than letting it reach the page |
 * | 3 | That call throws on an import carrying `undefined` before `services/api.ts` L9 reaches axios, so the collection request L8 builds is never issued |
 *
 * The container renders with no child, and therefore with no bounding box.
 *
 * Rendering the `undefined` `TweetCard` needs a non-empty collection to reach the map at
 * L59-L61, which L32 throwing makes unreachable from this route; that ceiling is covered by
 * `frontend/src/components/TweetManagement.test.tsx`.
 *
 * @see e2e/README.md - adding a spec to this directory.
 * @see docs/testing/DECISION-LOG.md - the interception, ceiling and layer-boundary rows for this file.
 */

import { expect, test, unInterceptedApiRequestUrls } from './harness-fixtures';

/* -------------------------------------------------------------------------- */
/* Oracles                                                                    */
/* -------------------------------------------------------------------------- */

/** Client route `e2e/harness/main.tsx` L71 mounts the subject at. Resolved against `use.baseURL`. */
const TWEET_LIST_ROUTE = '/tweets';

/** Container element `components/TweetManagement` L58 renders. */
const TWEET_LIST_CONTAINER = 'div.tweet-list';

/**
 * Globs covering the collection request `services/api.ts` L8 builds. Both match that request,
 * and Playwright runs a single matching handler per request, so no test below asserts which
 * glob fired. The document request for {@link TWEET_LIST_ROUTE} also matches the first of
 * them, which is what every handler's navigation guard hands back to the harness.
 */
const TWEET_COLLECTION_GLOBS = ['**/tweets*', '**/undefined/tweets*'] as const;

/** Prefix `components/TweetManagement` L35 passes to `console.error`. */
const FETCH_FAILURE_PREFIX = 'Error fetching tweets:';

/** How a browser reports the call at L32 against an import that carries `undefined`. */
const UNCALLABLE_IMPORT = /is not a function/;

/** The name L2 imports, which `services/twitterService` does not declare. */
const MISSING_EXPORT_NAME = /getTweets/;

/** Prefix an uncaught error is recorded under, as opposed to a console message. */
const PAGE_ERROR_PREFIX = 'pageerror:';

/** Budget for a poll over state the mount effect at L25-L27 has to settle first. */
const SETTLE_TIMEOUT_MS = 10_000;

test.describe('harness route /tweets - TweetList (frontend/src/components/TweetManagement)', () => {
  test('renders an empty tweet-list container', async ({ page }) => {
    const interceptedUrls: string[] = [];
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`${PAGE_ERROR_PREFIX} ${error.message}`));

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
      await test.info().attach('browser-diagnostics', {
        body: diagnostics.join('\n') || '(no console message and no page error)',
        contentType: 'text/plain',
      });
    }
  });

  test('logs the fetch failure because twitterService declares no getTweets export', async ({
    page,
  }) => {
    const interceptedUrls: string[] = [];
    const diagnostics: string[] = [];
    const consoleErrors: string[] = [];

    // Console errors are recorded separately from the diagnostics ledger, which also carries
    // the dev-server and React notices.
    page.on('console', (message) => {
      diagnostics.push(`console.${message.type()}: ${message.text()}`);

      if (message.type() === 'error') {
        consoleErrors.push(message.text());
      }
    });
    page.on('pageerror', (error) => diagnostics.push(`${PAGE_ERROR_PREFIX} ${error.message}`));

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
        .poll(() => consoleErrors.filter((text) => text.includes(FETCH_FAILURE_PREFIX)).length, {
          message: `expected exactly one console error carrying "${FETCH_FAILURE_PREFIX}"`,
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toBe(1);

      const [reported] = consoleErrors.filter((text) => text.includes(FETCH_FAILURE_PREFIX));

      // One message carries the production prefix and what the call at L32 was made against.
      expect(reported).toMatch(UNCALLABLE_IMPORT);
      expect(reported).toMatch(MISSING_EXPORT_NAME);

      // L34-L36 swallowed it: nothing reached the page as an uncaught error, and the route
      // stayed mounted.
      expect(diagnostics.filter((entry) => entry.startsWith(PAGE_ERROR_PREFIX))).toEqual([]);
      await expect(page.locator(TWEET_LIST_CONTAINER)).toBeAttached();
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
      await test.info().attach('browser-diagnostics', {
        body: diagnostics.join('\n') || '(no console message and no page error)',
        contentType: 'text/plain',
      });
    }
  });

  test('issues no tweet collection request because the uncallable import throws before axios', async ({
    page,
  }) => {
    const interceptedUrls: string[] = [];
    const diagnostics: string[] = [];
    const consoleErrors: string[] = [];

    page.on('console', (message) => {
      diagnostics.push(`console.${message.type()}: ${message.text()}`);

      if (message.type() === 'error') {
        consoleErrors.push(message.text());
      }
    });
    page.on('pageerror', (error) => diagnostics.push(`${PAGE_ERROR_PREFIX} ${error.message}`));

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
        .poll(() => consoleErrors.filter((text) => text.includes(FETCH_FAILURE_PREFIX)).length, {
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
      await test.info().attach('browser-diagnostics', {
        body: diagnostics.join('\n') || '(no console message and no page error)',
        contentType: 'text/plain',
      });
    }
  });
});

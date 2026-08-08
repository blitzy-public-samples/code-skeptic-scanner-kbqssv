/**
 * End-to-end coverage of the harness client route `/`.
 *
 * Subject: `RealTimeFeed`, the default export of `frontend/src/components/Dashboard`,
 * which `e2e/harness/main.tsx` mounts at `/`. That module is an extension-less file;
 * `e2e/vite.harness.config.ts` resolves and transforms it.
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
 * | 1 | `components/Dashboard` L22-L23 render `div.real-time-feed` around `<h2>Real-Time Tweet Feed</h2>` |
 * | 2 | `components/Dashboard` L10 calls `getLatestTweets()` with no argument, once per mount, and `services/api.ts` L5-L9 build `undefined/tweets?page=undefined&limit=undefined` from it |
 * | 3 | `components/Dashboard` L24-L26 render every member of the collection through `TweetCard`, which no module exports |
 *
 * The 30-second `setInterval` at `components/Dashboard` L16 and the `clearInterval` at L18 are
 * covered by `frontend/src/components/Dashboard.test.tsx` under fake timers, not here.
 *
 * @see e2e/README.md - adding a spec to this directory.
 * @see docs/testing/DECISION-LOG.md - the interception, ceiling and layer-boundary rows for this file.
 */

import path from 'node:path';

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
 * Globs covering the collection request `services/api.ts` L8 builds. Both match that request,
 * and Playwright runs a single matching handler per request. Each test below registers one
 * handler function under every glob and records into one array.
 */
const TWEET_COLLECTION_GLOBS = ['**/tweets*', '**/undefined/tweets*'] as const;

/** Pathname of that request, after the browser resolves its relative URL against the harness origin. */
const TWEET_COLLECTION_PATHNAME = '/undefined/tweets';

/** Value `page` and `limit` each carry, being `String(undefined)`. */
const UNDEFINED_QUERY_VALUE = 'undefined';

/** Two-record collection payload, keyed as `frontend/src/schema/tweetSchema.ts` declares. */
const TWEETS_FIXTURE = path.join(__dirname, '..', 'fixtures', 'tweets.json');

/** React's report for an element type that resolved to `undefined`. */
const INVALID_ELEMENT_TYPE = /Element type is invalid/;

/** Value React names in that report, which is what the `TweetCard` specifier resolved to. */
const RESOLVED_ELEMENT_TYPE = /got: undefined/;

/** Component React attributes the invalid element type to. */
const REPORTING_COMPONENT = /Check the render method of `RealTimeFeed`/;

/**
 * Budget for a poll over state a mount fetch has to settle first. Below the 30000 ms
 * `setInterval` at `components/Dashboard` L16, so only the mount request falls inside it.
 */
const SETTLE_TIMEOUT_MS = 10_000;

test.describe('harness route / - RealTimeFeed (frontend/src/components/Dashboard)', () => {
  test('renders the Real-Time Tweet Feed heading inside the feed container', async ({ page }) => {
    const interceptedUrls: string[] = [];
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

    // An empty collection renders no `TweetCard`, leaving the container and its heading intact.
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

      // The map at L24-L26 produced no child, so the heading is the container's only element.
      await expect(container.locator('*')).toHaveCount(1);
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

  test('requests the tweet collection once per mount from the literal undefined base URL', async ({
    page,
  }) => {
    const interceptedUrls: string[] = [];
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

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
      await test.info().attach('browser-diagnostics', {
        body: diagnostics.join('\n') || '(no console message and no page error)',
        contentType: 'text/plain',
      });
    }
  });

  test('does not render tweet cards because TweetCard is exported by nothing', async ({ page }) => {
    const interceptedUrls: string[] = [];
    const diagnostics: string[] = [];

    // Both recorders are read: the failure surfaces as an uncaught error, a console error, or both.
    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

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
        .poll(() => diagnostics.join('\n'), {
          message: 'expected React to report an invalid element type for the undefined TweetCard',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toMatch(INVALID_ELEMENT_TYPE);

      // The same report names the resolved value and the component that rendered it.
      const reported = diagnostics.join('\n');
      expect(reported).toMatch(RESOLVED_ELEMENT_TYPE);
      expect(reported).toMatch(REPORTING_COMPONENT);

      // The invalid element type propagated out of the render, taking the route with it.
      await expect(page.locator(FEED_CONTAINER)).toHaveCount(0);
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

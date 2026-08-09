/**
 * The isolation property every other spec in this directory depends on, asserted directly.
 *
 * Subject: the interaction between a spec's own `page.route(...)` and the catch-all
 * `context.route('**\/*')` the `noEgress` fixture in `./harness-fixtures.ts` installs. Playwright
 * evaluates page routes before context routes, so a spec route that matches a request answers it and
 * the fixture never sees it. That ordering is what makes the *shape* of a spec's pattern a
 * correctness property rather than a matter of taste:
 *
 * - A host-agnostic pattern - `'**\/api/config/twitter'`, say - matches that path on **any** origin.
 *   A handler registered under it fulfils a request the page addressed to a foreign host, the
 *   assertions on the recorded body all pass, and nothing anywhere records that the request left the
 *   harness. For the credential endpoint that is a green test over credentials sent elsewhere.
 * - A pattern anchored to {@link HARNESS_ORIGIN} matches only the harness. A foreign origin on the
 *   same path falls through to the fixture, which aborts it `blockedbyclient` and records it.
 *
 * Every pattern in `./dashboard.spec.ts`, `./tweets.spec.ts`, `./analytics.spec.ts` and
 * `./configuration.spec.ts` is anchored. This file proves the anchoring holds, for each of the four
 * request shapes those specs intercept, by driving both halves of the contrast in one test:
 *
 * | Step | Request | Expected disposition |
 * |------|---------|----------------------|
 * | 1 | {@link HARNESS_ORIGIN} + the path | claimed by this spec's own route, recorded by it, answered `200` |
 * | 2 | {@link FOREIGN_ORIGIN} + the same path | not claimed; aborted by the fixture and entered in its ledger |
 *
 * Step 2 deliberately causes the breach the fixture exists to detect, so each test acknowledges it
 * with {@link consumeAbortedRequestUrls} - after asserting the exact URL - which is what keeps
 * teardown from failing the very test that proved the property.
 *
 * Both requests are issued from the `/configuration` route. `frontend/src/components/Configuration`
 * declares no mount effect, so that page issues no request of its own and every entry in either
 * ledger belongs to this file.
 *
 * @see e2e/tests/harness-fixtures.ts - the fixture under test and the ledger contract.
 * @see e2e/README.md - the isolation guarantees this layer offers.
 * @see docs/testing/DECISION-LOG.md - rows D130, D131 and D213.
 */

import type { Page } from '@playwright/test';

import {
  blockedByEgressGuard,
  consumeAbortedRequestUrls,
  expect,
  HARNESS_ORIGIN,
  test,
} from './harness-fixtures';

/* -------------------------------------------------------------------------- */
/* Oracles                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Client route both requests are issued from. `harness/main.tsx` mounts
 * `frontend/src/components/Configuration` here, and that component fetches nothing on mount.
 */
const QUIET_ROUTE = '/configuration';

/**
 * Origin standing in for "anywhere that is not the harness".
 *
 * A reserved-for-documentation domain (RFC 2606), so it names no real service, and one that shares a
 * path with the harness rather than differing from it - the point being that the path is identical
 * and only the host differs.
 */
const FOREIGN_ORIGIN = 'https://tweets.example.com';

/** Status this spec's own route answers a harness-origin request with. */
const CLAIMED_STATUS = 200;

/**
 * Every request shape a spec in this directory installs a route for.
 *
 * `pattern` is the path portion appended to an origin to build a Playwright glob; `probe` is the
 * path portion of the URL each step requests. Keeping the two separate is what lets one test drive
 * the same pattern against two origins.
 */
const INTERCEPTED_SHAPES = [
  {
    what: 'the tweet collection the dashboard and tweet-list flows intercept',
    pattern: '/undefined/tweets*',
    probe: '/undefined/tweets?page=undefined&limit=undefined',
    method: 'GET',
  },
  {
    what: 'the tweet collection under a configured base URL',
    pattern: '/tweets*',
    probe: '/tweets?page=2&limit=10',
    method: 'GET',
  },
  {
    what: 'the trend series the analytics flow intercepts',
    pattern: '/api/trends*',
    probe: '/api/trends?start=2024-01-01&end=2024-01-31',
    method: 'GET',
  },
  {
    what: 'the credential write the configuration flow intercepts',
    pattern: '/api/config/twitter',
    probe: '/api/config/twitter',
    method: 'POST',
  },
] as const;

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

/** What a `fetch` issued inside the page did. */
type FetchOutcome =
  | { readonly settled: 'resolved'; readonly status: number }
  | { readonly settled: 'rejected'; readonly message: string };

/**
 * Issues one request from inside the page and reports how it settled, without letting a rejection
 * escape as an unhandled one.
 *
 * Run in the page rather than through `request.fetch` deliberately: `page.route` and
 * `context.route` intercept what the *page* issues, and an APIRequestContext call would bypass the
 * very layer under test.
 *
 * @param page - Page to issue the request from.
 * @param url - Absolute URL to request.
 * @param method - HTTP method; `POST` carries a JSON body, matching the credential write.
 */
async function fetchFromPage(page: Page, url: string, method: string): Promise<FetchOutcome> {
  return page.evaluate(async ({ url: target, method: verb }): Promise<FetchOutcome> => {
    const init: RequestInit =
      verb === 'POST'
        ? { method: verb, headers: { 'Content-Type': 'application/json' }, body: '{}' }
        : { method: verb };

    try {
      const response = await fetch(target, init);
      return { settled: 'resolved', status: response.status };
    } catch (error) {
      return { settled: 'rejected', message: (error as Error).message };
    }
  }, { url, method });
}

test.describe('harness isolation - an anchored spec route claims only the harness origin', () => {
  for (const shape of INTERCEPTED_SHAPES) {
    test(`does not let a foreign origin borrow the route for ${shape.what}`, async ({
      page,
      browserDiagnostics,
    }) => {
      const claimed: string[] = [];

      /*
       * This test causes the abort it asserts, and Chrome reports an aborted request as a console
       * error, so the notice is declared rather than tolerated: the automatic diagnostics fixture
       * fails any test carrying an error it did not name, and step 2 below is exactly such an error.
       * Nothing else is declared, so a second, unrelated error still fails this test.
       */
      browserDiagnostics.allow(blockedByEgressGuard());

      // The corrected pattern: anchored to the harness origin, exactly as the four flow specs
      // spell theirs.
      await page.route(`${HARNESS_ORIGIN}${shape.pattern}`, async (route) => {
        claimed.push(route.request().url());
        await route.fulfill({ status: CLAIMED_STATUS, json: [] });
      });

      await page.goto(QUIET_ROUTE);

      const harnessUrl = `${HARNESS_ORIGIN}${shape.probe}`;
      const foreignUrl = `${FOREIGN_ORIGIN}${shape.probe}`;

      try {
        // Step 1 - the harness origin is claimed by this spec's route.
        const onHarness = await fetchFromPage(page, harnessUrl, shape.method);

        expect(onHarness).toEqual({ settled: 'resolved', status: CLAIMED_STATUS });
        expect(claimed).toEqual([harnessUrl]);

        // Nothing reached the dev server: an un-intercepted harness API path would have been
        // answered 503 and entered in the fixture's second ledger, failing this test at teardown.

        // Step 2 - the same path on a foreign origin is not claimed.
        const offHarness = await fetchFromPage(page, foreignUrl, shape.method);

        expect(offHarness.settled).toBe('rejected');
        expect(claimed).toEqual([harnessUrl]);

        // ...it reached the fixture instead, which aborted it and recorded it. Asserted first,
        // then consumed, so teardown does not fail the test that proved the property.
        expect(consumeAbortedRequestUrls()).toEqual([foreignUrl]);
      } finally {
        await test.info().attach('claimed-by-this-spec', {
          body: claimed.join('\n') || '(no request claimed)',
          contentType: 'text/plain',
        });
      }
    });
  }
});

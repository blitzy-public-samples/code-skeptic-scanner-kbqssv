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
 * Step 2 provokes the breach the fixture exists to detect, so each test acknowledges it with
 * {@link consumeAbortedRequestUrls} - after asserting the exact URL - which is what lets the test
 * that proved the property reach teardown green.
 *
 * Both requests are issued from the `/configuration` route. `frontend/src/components/Configuration`
 * declares no mount effect, so that page issues no request of its own and every entry in either
 * ledger belongs to this file.
 *
 * ## The second describe: the same-origin boundary
 *
 * Anchoring answers "may a spec route claim a foreign origin". It says nothing about a request the page
 * addresses to the harness itself on a path the harness does not serve, and two of those are not
 * ordinary 404s:
 *
 * - a **dev-server control endpoint** under `/__`, which makes the Node process launch an editor or
 *   read the filesystem on the page's behalf;
 * - a **`/@id/` virtual-module id** the harness never registered, or a root-relative **traversal**,
 *   either of which ends in Vite's own resolution rather than in the harness graph.
 *
 * Both layers are asserted separately, because they fail independently. The browser layer is the
 * `noEgress` fixture, driven with a page `fetch`. The server layer is `harnessFilesystemGuard` in
 * `../vite.harness.config.ts`, driven with `request.fetch` - Playwright's APIRequestContext, which no
 * `page.route` or `context.route` intercepts, so a 403 there is the middleware's answer and not a
 * browser-side rule standing in for it. The last test then loads a route that *is* in the graph, so the
 * containment cannot pass by refusing everything.
 *
 * @see e2e/tests/harness-fixtures.ts - the fixture under test and the ledger contract.
 * @see e2e/README.md - the isolation guarantees this layer offers.
 * @see docs/testing/DECISION-LOG.md - rows D130, D131, D213 and D317.
 */

import http from 'node:http';

import type { Page } from '@playwright/test';

import {
  blockedByEgressGuard,
  consumeAbortedRequestUrls,
  consumeDeniedControlPathUrls,
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

/** Status `harnessFilesystemGuard` in `../vite.harness.config.ts` refuses with. */
const FORBIDDEN_STATUS = 403;

/** Body it refuses with, asserted so a 403 from anything else would not satisfy these tests. */
const FORBIDDEN_BODY = '403 Forbidden';

/** Accessible name of the `<h2>` the `/configuration` route renders when it mounts. */
const QUIET_ROUTE_HEADING = 'Twitter API Settings';

/**
 * Every spelling of Vite's open-in-editor endpoint that `connect` would route to the editor launcher.
 *
 * `middlewares.use('/__open-in-editor', …)` matches case-insensitively and admits the route followed by
 * nothing, by `/`, by a sub-path or by a query string, so all five reach the same handler - which
 * resolves the `file` parameter and spawns an editor process. An equality test against the first entry
 * refuses only that one.
 *
 * The `file` values are UNC and traversal shapes: harmless because the endpoint is refused, and they
 * name what the refusal is protecting.
 */
const EDITOR_SPELLINGS = [
  '/__open-in-editor?file=harness.tsx',
  '/__open-in-editor/?file=harness.tsx',
  '/__open-in-editor/anything?file=harness.tsx',
  '/__OPEN-IN-EDITOR?file=harness.tsx',
  '/__open-in-editor?file=%5C%5Cattacker.example%5Cshare%5Cx',
] as const;

/**
 * Same-origin paths that address neither the harness graph nor a control endpoint, and must not be
 * served.
 *
 * The first two are `/@id/` requests: that prefix carries a module id rather than a path, and only the
 * ids this configuration registered are harness modules. An unregistered one used to skip every check
 * in the guard. The rest are root-relative traversals: `resolveRootRelativePath` keeps `..` segments, so
 * each resolves outside `e2e/harness` while matching no denied *name* - which is why containment, not
 * the deny list, is what refuses them.
 */
const OUT_OF_GRAPH_PATHS = [
  {
    what: 'an unregistered virtual module id',
    path: '/@id/__x00__extless:C:/not/a/harness/module',
  },
  {
    what: 'a traversal dressed as a virtual module id',
    path: '/@id/../../package.json',
  },
  {
    what: 'an encoded traversal onto a file outside the harness root',
    path: '/%2e%2e/%2e%2e/frontend/package.json',
  },
  {
    what: 'a plain traversal onto the repository root',
    path: '/../../package.json',
  },
] as const;

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
 * Run in the page: `page.route` and `context.route` intercept what the *page* issues, so an
 * APIRequestContext call does not reach the layer under test.
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

/**
 * Issues one GET to the harness with the request line **exactly** as given, and reports the status and
 * body.
 *
 * `node:http` is used rather than `request.fetch` or a page `fetch` because every HTTP client that
 * parses a URL first normalises the path: Chromium and Playwright's APIRequestContext both collapse
 * `..` segments and decode `%2e`, so a traversal probe sent through either arrives at the server as an
 * already-resolved path and tests nothing. A raw request line is what a traversal actually looks like on
 * the wire, and it is the only way to put one in front of the middleware.
 *
 * @param path - Request target, sent verbatim; not encoded, normalised or validated.
 */
async function requestRawPath(path: string): Promise<{ status: number; body: string }> {
  const { hostname, port } = new URL(HARNESS_ORIGIN);

  return new Promise((resolve, reject) => {
    const request = http.request(
      { host: hostname, port, path, method: 'GET' },
      (response) => {
        const chunks: Buffer[] = [];
        response.on('data', (chunk: Buffer) => chunks.push(chunk));
        response.on('end', () =>
          resolve({
            status: response.statusCode ?? 0,
            body: Buffer.concat(chunks).toString('utf8'),
          }),
        );
      },
    );

    request.on('error', reject);
    request.end();
  });
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

test.describe('harness isolation - a same-origin dev-server control path is refused twice', () => {
  test('the browser layer aborts and records it before it leaves the page', async ({
    page,
    browserDiagnostics,
  }) => {
    /*
     * The abort this test causes is reported by Chrome as a console error, exactly as the
     * foreign-origin case above is, so the notice is declared rather than tolerated.
     */
    browserDiagnostics.allow(blockedByEgressGuard());

    await page.goto(QUIET_ROUTE);

    const controlUrl = `${HARNESS_ORIGIN}${EDITOR_SPELLINGS[0]}`;
    const outcome = await fetchFromPage(page, controlUrl, 'GET');

    expect(outcome.settled).toBe('rejected');

    // Recorded, not merely blocked: the fallback branch it replaced left no trace at all.
    expect(consumeDeniedControlPathUrls()).toEqual([`GET ${controlUrl}`]);
  });

  for (const spelling of EDITOR_SPELLINGS) {
    test(`the dev server answers 403 to the editor endpoint spelled ${spelling}`, async ({
      request,
    }) => {
      /*
       * `request.fetch` uses Playwright's APIRequestContext, which is not routed by `page.route` or by
       * the `noEgress` fixture, so this assertion is about the middleware in
       * `e2e/vite.harness.config.ts` and nothing else. Without it the browser-side abort above would be
       * the only evidence, and it cannot speak for a request that does not come from a page.
       */
      const response = await request.fetch(`${HARNESS_ORIGIN}${spelling}`, {
        method: 'GET',
        failOnStatusCode: false,
      });

      expect(response.status()).toBe(FORBIDDEN_STATUS);
      expect(await response.text()).toBe(FORBIDDEN_BODY);
    });
  }

  for (const shape of OUT_OF_GRAPH_PATHS) {
    test(`the dev server answers 403 to ${shape.what}`, async () => {
      const response = await requestRawPath(shape.path);

      expect(response.status).toBe(FORBIDDEN_STATUS);
      expect(response.body).toBe(FORBIDDEN_BODY);
    });
  }

  test('while the module graph the harness does serve still loads', async ({ page }) => {
    /*
     * The other half of every refusal: containment that also refused a legitimate module would turn a
     * green suite red for the right reason and the wrong cause. The `/configuration` route is mounted
     * through a registered virtual module - one of the four extension-less component files - so a
     * rendered heading here is proof that the `/@id/` allow-list admits what it should.
     */
    await page.goto(QUIET_ROUTE);

    await expect(page.getByRole('heading', { level: 2 })).toHaveText(QUIET_ROUTE_HEADING);
  });
});

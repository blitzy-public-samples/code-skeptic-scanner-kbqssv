/**
 * End-to-end coverage of the harness client route `/analytics`.
 *
 * Subject: `TrendCharts`, the default export of `frontend/src/components/Analytics`, which
 * `e2e/harness/main.tsx` mounts at `/analytics` (L75) with its module-scope
 * `ANALYTICS_DATE_RANGE` (L41-L44) as the `dateRange` prop. That module is an extension-less
 * file; `e2e/vite.harness.config.ts` resolves and transforms it.
 *
 * `test` and `expect` come from `./harness-fixtures`, whose automatic `noEgress` fixture aborts
 * every request addressed off the harness origin and fails the test at teardown for any harness
 * API request no route below claimed. `/api/trends` is one of those paths, so each test installs
 * its own interception before navigating, and holds no state shared with another test.
 *
 * The trend request is issued by `e2e/harness/stubs/analyticsService.ts`, the harness stand-in
 * for the `@/services/analyticsService` specifier the subject imports. That stub never resolves,
 * and the response a test fulfils with selects which rejection the subject catches:
 *
 * | Fulfilment | Rejection |
 * |------------|-----------|
 * | Non-ok status | a status `Error`, thrown before any body is parsed |
 * | Ok, body is not a trend series | `TrendSeriesContractError` |
 * | Ok, body is a trend series | `UnrenderableTrendSeriesError` |
 *
 * What each test asserts, and the lines it reads from:
 *
 * | Test | Behaviour asserted |
 * |------|--------------------|
 * | 1 | `components/Analytics` L18-L20 catch a failed trend request and log it, leaving the L66-L69 heading and canvas mounted |
 * | 2 | `components/Analytics` L16 calls `getTrendData(dateRange)` once per mount, and `harness/stubs/analyticsService.ts` L156 builds `/api/trends?start=…&end=…` from that argument |
 * | 3 | `components/Analytics` L40 constructs a `Chart` from the tree-shakeable L2 export, which no module registers. Skipped; the skip carries its reason |
 *
 * `frontend/src/components/Analytics.test.tsx` covers the same component under jsdom with
 * `getTrendData` mocked, which is the layer where a resolving trend request is exercised.
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
const CHARTS_ROUTE = '/analytics';

/**
 * Wrapper `components/Analytics` L66 renders. It carries no class, and `harness/main.tsx` L64-L78
 * renders one route element inside the document's single `<main>` landmark, so this selector
 * matches that wrapper and nothing else.
 */
const CHARTS_CONTAINER = 'main > div';

/** Accessible name of the `<h2>` `components/Analytics` L67 renders. */
const CHARTS_HEADING = 'Trend Charts';

/** Heading level of that element. */
const CHARTS_HEADING_LEVEL = 2;

/** Canvas `components/Analytics` L68 renders, which L38 looks up by id. */
const CHART_CANVAS = 'canvas#trendChart';

/** Element descendants of the wrapper: the heading and the canvas, and nothing else. */
const CHARTS_CONTAINER_CHILD_COUNT = 2;

/** Glob covering the trend request `harness/stubs/analyticsService.ts` L156 builds. */
const TREND_REQUEST_GLOB = '**/api/trends*';

/** Pathname of that request, after the browser resolves its relative URL against the harness origin. */
const TREND_REQUEST_PATHNAME = '/api/trends';

/** Method that stub's `fetch` call issues it with, no `RequestInit` being supplied. */
const TREND_REQUEST_METHOD = 'GET';

/** Query parameter that stub writes `dateRange.startDate` into. */
const RANGE_START_KEY = 'start';

/** Query parameter it writes `dateRange.endDate` into. */
const RANGE_END_KEY = 'end';

/** Both, in the order L156 writes them, being every parameter the request carries. */
const TREND_QUERY_KEYS = [RANGE_START_KEY, RANGE_END_KEY];

/** `startDate` of the `ANALYTICS_DATE_RANGE` prop, from `harness/main.tsx` L42. */
const RANGE_START = '2024-01-01';

/** `endDate` of that prop, from `harness/main.tsx` L43. */
const RANGE_END = '2024-01-31';

/** Status that drives the stub's status-error rejection. */
const TREND_REQUEST_FAILURE_STATUS = 500;

/** Six-point series payload, shaped as `harness/stubs/analyticsService.ts` declares `TrendSeries`. */
const TRENDS_FIXTURE = path.join(__dirname, '..', 'fixtures', 'trends.json');

/** Prefix `components/Analytics` L19 logs a caught trend-request failure under. */
const TREND_FAILURE_LOG = /Error fetching trend data:/;

/** Chart.js report for a chart part that was never passed to `Chart.register`. */
const UNREGISTERED_CHART_PART = /not a registered (scale|controller)/;

/** Budget for a poll over state the mount request has to settle first. */
const SETTLE_TIMEOUT_MS = 10_000;

/**
 * Whether `harness/stubs/analyticsService.ts` forwards a well-formed `TrendSeries` to the subject.
 * It rejects on every path, so the subject's `chartData` state stays `null` and the effect at
 * `components/Analytics` L26-L30 never calls `renderCharts`.
 */
const HARNESS_FORWARDS_TREND_SERIES = false;

/** Blocker recorded on the test that needs a forwarded series. */
const CHART_REGISTRATION_SKIP_REASON =
  'frontend/src/components/Analytics L2 imports the tree-shakeable { Chart } export and no module ' +
  'calls Chart.register, so L40 cannot construct a chart. Reaching L40 needs a resolved trend ' +
  'series, and e2e/harness/stubs/analyticsService.ts rejects on every path, so this layer cannot ' +
  'observe the failure. frontend/src/components/Analytics.test.tsx mocks getTrendData and covers it.';

test.describe('harness route /analytics - TrendCharts (frontend/src/components/Analytics)', () => {
  test('swallows a failed trend request and keeps the heading and canvas mounted', async ({
    page,
  }) => {
    const interceptedUrls: string[] = [];
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

    // A non-ok status rejects inside the stub before any body is parsed, so `chartData` stays
    // null and the effect at L26-L30 never calls `renderCharts`.
    await page.route(TREND_REQUEST_GLOB, async (route) => {
      interceptedUrls.push(route.request().url());
      await route.fulfill({ status: TREND_REQUEST_FAILURE_STATUS, json: {} });
    });

    await page.goto(CHARTS_ROUTE);

    try {
      const container = page.locator(CHARTS_CONTAINER);
      await expect(container).toBeVisible();

      await expect(
        container.getByRole('heading', {
          level: CHARTS_HEADING_LEVEL,
          name: CHARTS_HEADING,
          exact: true,
        }),
      ).toBeVisible();

      // Carries no width or height attribute, so it takes the default 300x150 intrinsic box.
      await expect(container.locator(CHART_CANVAS)).toBeVisible();

      // L66-L69 render these two elements and nothing else.
      await expect(container.locator('*')).toHaveCount(CHARTS_CONTAINER_CHILD_COUNT);

      await expect
        .poll(() => diagnostics.join('\n'), {
          message: `expected the subject to log the caught failure under ${TREND_FAILURE_LOG}`,
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toMatch(TREND_FAILURE_LOG);

      // The rejection was caught at L18-L20, so it never reached the page as an uncaught error.
      await expect(container).toBeVisible();
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

  test('requests the trend series once per mount for the harness date range', async ({ page }) => {
    const interceptedUrls: string[] = [];
    const interceptedMethods: string[] = [];
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

    await page.route(TREND_REQUEST_GLOB, async (route) => {
      const request = route.request();
      interceptedMethods.push(request.method());
      interceptedUrls.push(request.url());
      await route.fulfill({ path: TRENDS_FIXTURE, contentType: 'application/json' });
    });

    await page.goto(CHARTS_ROUTE);

    try {
      // One mount, one fetch: `harness/main.tsx` mounts the subject outside `React.StrictMode`,
      // and its `ANALYTICS_DATE_RANGE` prop keeps one identity, so the L13-L24 effect fires once.
      await expect
        .poll(() => interceptedUrls.length, {
          message: `expected exactly one ${TREND_REQUEST_PATHNAME} request, recorded ${JSON.stringify(interceptedUrls)}`,
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toBe(1);

      expect(interceptedMethods[0]).toBe(TREND_REQUEST_METHOD);

      const requested = new URL(interceptedUrls[0]);

      // A relative URL, so the browser resolved it against the harness origin.
      expect(requested.origin).toBe(HARNESS_ORIGIN);
      expect(requested.pathname).toBe(TREND_REQUEST_PATHNAME);

      // L156 interpolates the two members of the prop, and adds no other parameter.
      expect([...requested.searchParams.keys()]).toEqual(TREND_QUERY_KEYS);
      expect(requested.searchParams.get(RANGE_START_KEY)).toBe(RANGE_START);
      expect(requested.searchParams.get(RANGE_END_KEY)).toBe(RANGE_END);

      // The subject logs the caught rejection only after consuming the response, so a second
      // mount fetch would have been recorded by the time this settles.
      await expect
        .poll(() => diagnostics.join('\n'), {
          message: 'expected the subject to consume the fulfilled series and log its rejection',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toMatch(TREND_FAILURE_LOG);

      expect(interceptedUrls).toHaveLength(1);
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

  test('does not paint a chart because Chart.register is never called', async ({ page }) => {
    test.skip(!HARNESS_FORWARDS_TREND_SERIES, CHART_REGISTRATION_SKIP_REASON);

    const interceptedUrls: string[] = [];
    const diagnostics: string[] = [];

    // Both recorders are read: an unregistered chart part surfaces as an uncaught error, a
    // console error, or both.
    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

    // A well-formed series is what carries the subject past the L27 guard into `renderCharts`.
    await page.route(TREND_REQUEST_GLOB, async (route) => {
      interceptedUrls.push(route.request().url());
      await route.fulfill({ path: TRENDS_FIXTURE, contentType: 'application/json' });
    });

    await page.goto(CHARTS_ROUTE);

    try {
      await expect
        .poll(() => diagnostics.join('\n'), {
          message: 'expected Chart.js to report a chart part that no module registered',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toMatch(UNREGISTERED_CHART_PART);
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

/**
 * End-to-end coverage of the harness client route `/analytics`.
 *
 * Subject: `TrendCharts`, the default export of `frontend/src/components/Analytics`, which
 * `e2e/harness/main.tsx` mounts at `/analytics` with its module-scope `ANALYTICS_DATE_RANGE`
 * as the `dateRange` prop. That module is an extension-less file; `e2e/vite.harness.config.ts`
 * resolves and transforms it.
 *
 * `test` and `expect` come from `./harness-fixtures`, whose two automatic fixtures do the
 * cross-cutting work: `noEgress` aborts every request addressed off the harness origin and fails
 * the test at teardown for any harness API request no route below claimed, and
 * `browserDiagnostics` attaches the browser's console and page errors and fails the test on any
 * it did not declare. `/api/trends` is one of those API paths, so each test installs its own
 * interception before navigating, declares the failures it expects, and holds no state shared
 * with another test.
 *
 * The trend request is issued by `e2e/harness/stubs/analyticsService.ts`, the harness stand-in
 * for the `@/services/analyticsService` specifier the subject imports. That stub rejects by
 * default, and the response a test fulfils with selects which path the subject takes:
 *
 * | Fulfilment | Outcome |
 * |------------|---------|
 * | Non-ok status | a status `Error`, thrown before any body is parsed |
 * | Ok, body is not a trend series | `TrendSeriesContractError` |
 * | Ok, body is a trend series | `UnrenderableTrendSeriesError` |
 * | Ok, a trend series, `FORWARD_TREND_SERIES_HEADER` set | resolves, carrying the subject into `renderCharts` |
 *
 * What each test asserts, in declaration order:
 *
 * | Test | Behaviour asserted |
 * |------|--------------------|
 * | 1 | `components/Analytics` L18-L20 catch a failed trend request and log it, leaving the L66-L69 heading and canvas mounted |
 * | 2 | `components/Analytics` L16 calls `getTrendData(dateRange)` once per mount, and `harness/stubs/analyticsService.ts` builds `/api/trends?start=…&end=…` from that argument |
 * | 3 | The L68 canvas is absent from the browser's accessibility tree, so the analytics content reaches assistive technology not at all |
 * | 4 | `components/Analytics` L40 constructs a `Chart` from the tree-shakeable L2 export that no module registers, which throws out of the L26-L30 effect and takes the route down |
 *
 * Tests 1 to 3 leave the stub on its default rejecting path. Test 4 is the one place in this suite
 * that opts into the forwarding path, and the only place in the repository where the
 * missing-`Chart.register` ceiling is *observed* rather than described: a real browser hands
 * `renderCharts` a live 2D context, so Chart.js gets as far as looking a chart part up in an empty
 * registry. Under jsdom there is no 2D context at all, and `chart.js` reports that and returns
 * before any registry lookup happens.
 *
 * `frontend/src/components/Analytics.test.tsx` covers the same component under jsdom with
 * `getTrendData` mocked. That is where a *resolving* trend request is exercised without this
 * consequence - the constructor is substituted, so the subject's chart configuration can be
 * asserted while it stays mounted.
 *
 * ## Which chart path each test reaches
 *
 * The subject's only `try`/`catch` wraps the `getTrendData` call at L16-L21; `renderCharts` and the
 * `new Chart(...)` inside it are wrapped by nothing, so "the failure was caught" is never a correct
 * description of a chart outcome. Two distinct paths are reached here, and keeping them apart is the
 * whole point of making forwarding opt-in:
 *
 * - **Tests 1 to 3 - the transport path.** `harness/stubs/analyticsService.ts` rejects, `chartData`
 *   stays `null`, and `renderCharts` is never entered. Test 1's subject is the caught *trend
 *   request*, never chart construction, which is what leaves the heading and canvas standing for
 *   tests 2 and 3 to read.
 * - **Test 4 - the construction path.** With the stub's forwarding header set, the context is
 *   acquired, the unregistered `'line'` controller raises, and the error propagates out of an
 *   unwrapped passive effect and unmounts the subject. Test 4 asserts each of those three, so the
 *   ceiling is measured in a real browser rather than left as a description.
 *
 * ## The canvas carries no accessible name - a documented ceiling
 *
 * L68 renders `<canvas id="trendChart"></canvas>` with no `role`, no `aria-label`, no
 * `aria-labelledby`, no `title`, no fallback child content and no table or textual summary beside it.
 * A canvas has no implicit ARIA role, so the element is simply not in the accessibility tree and the
 * whole of the analytics content is unavailable to a screen reader - the heading is all that is
 * announced. Test 3 asserts that in a real browser rather than inferring it, so supplying a name or a
 * text alternative becomes a deliberate, test-visible change.
 *
 * @see e2e/README.md - adding a spec to this directory.
 * @see frontend/src/components/Analytics.test.tsx - the jsdom layer for the same component.
 * @see docs/testing/DECISION-LOG.md - the interception, ceiling and layer-boundary rows for this
 *   file, including rows D231, D345 and D346.
 */

import path from 'node:path';

import {
  FORWARD_TREND_SERIES_HEADER,
  FORWARD_TREND_SERIES_VALUE,
} from '../harness/stubs/analyticsService';
import { expect, HARNESS_ORIGIN, resourceFailure, test } from './harness-fixtures';

/* -------------------------------------------------------------------------- */
/* Oracles                                                                    */
/* -------------------------------------------------------------------------- */

/** Client route `e2e/harness/main.tsx` mounts the subject at. Resolved against `use.baseURL`. */
const CHARTS_ROUTE = '/analytics';

/**
 * Wrapper `components/Analytics` L66 renders. It carries no class, and `harness/main.tsx` renders one
 * route element inside the document's single `<main>` landmark, so this selector matches that wrapper
 * and nothing else.
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

/**
 * Glob covering the trend request `harness/stubs/analyticsService.ts` L156 builds.
 *
 * Anchored to {@link HARNESS_ORIGIN}, so the pattern claims only requests addressed to the harness
 * origin. A request to a foreign host that shares this path matches nothing, falls through to the
 * `noEgress` fixture, and is aborted and recorded. `./isolation.spec.ts` asserts exactly that.
 */
const TREND_REQUEST_GLOB = `${HARNESS_ORIGIN}/api/trends*`;

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

/** `startDate` of the `ANALYTICS_DATE_RANGE` prop the harness passes to the subject. */
const RANGE_START = '2024-01-01';

/** `endDate` of that prop. */
const RANGE_END = '2024-01-31';

/** Status that drives the stub's status-error rejection. */
const TREND_REQUEST_FAILURE_STATUS = 500;

/** Six-point series payload, shaped as `harness/stubs/analyticsService.ts` declares `TrendSeries`. */
const TRENDS_FIXTURE = path.join(__dirname, '..', 'fixtures', 'trends.json');

/** Prefix `components/Analytics` L19 logs a caught trend-request failure under. */
const TREND_FAILURE_LOG = /Error fetching trend data:/;

/** {@link TREND_FAILURE_LOG} as an allow-list pattern, keyed on the console record's rendered form. */
const EXPECTED_TREND_FAILURE = /console\.error: Error fetching trend data:/;

/**
 * Chart.js report for a chart part that was never passed to `Chart.register`.
 *
 * Either half can come first: Chart.js resolves the `type: 'line'` controller and the `y` scale
 * from the same empty registry, and which lookup it performs first is its own internal order, not
 * a property of the subject.
 */
const UNREGISTERED_CHART_PART = /not a registered (scale|controller)/;

/** How React attributes an error thrown out of a passive effect to the component that owns it. */
const REPORTING_COMPONENT = /TrendCharts/;

/** Budget for a poll over state the mount request has to settle first. */
const SETTLE_TIMEOUT_MS = 10_000;

/**
 * Every attribute that could give {@link CHART_CANVAS} an accessible name or put it in the
 * accessibility tree. The subject sets none of them; each absence is asserted individually so a
 * failure names the one that appeared.
 */
const CANVAS_NAMING_ATTRIBUTES = [
  'role',
  'aria-label',
  'aria-labelledby',
  'aria-describedby',
  'title',
] as const;

/** Roles a named or role-bearing chart canvas would contribute to the tree. None is present. */
const CANVAS_CANDIDATE_ROLES = ['image', 'img', 'figure', 'canvas', 'graphics-document'] as const;

/** Role of the one element the subject does contribute, its L67 heading. */
const HEADING_ROLE = 'heading';

/** One node of Chromium's accessibility tree, as `page.accessibility.snapshot` reports it. */
interface AccessibilityNode {
  role?: string;
  children?: AccessibilityNode[];
}

/**
 * Flattens an accessibility snapshot to the set of roles it contains.
 *
 * @param node - Root of the snapshot, or `null` when the page contributed none.
 * @returns Every `role` in the subtree, root included, in document order.
 */
function collectRoles(node: AccessibilityNode | null): string[] {
  if (node === null) {
    return [];
  }

  const here = node.role === undefined ? [] : [node.role];
  const below = (node.children ?? []).flatMap((child) => collectRoles(child));

  return [...here, ...below];
}

/**
 * Response headers that opt `harness/stubs/analyticsService.ts` into forwarding a well-formed
 * `TrendSeries` to the subject instead of rejecting.
 *
 * Without them the stub rejects on every path, so the subject's `chartData` state stays `null` and
 * the effect at `components/Analytics` L26-L30 never calls `renderCharts` - which is what tests 1
 * to 3 rely on. Only test 4 sets them, and only because the unmount that follows is what it
 * asserts. Both names come from the stub itself, so the contract is written in exactly one place.
 */
const FORWARD_TREND_SERIES_HEADERS = {
  [FORWARD_TREND_SERIES_HEADER]: FORWARD_TREND_SERIES_VALUE,
} as const;

test.describe('harness route /analytics - TrendCharts (frontend/src/components/Analytics)', () => {
  test('swallows a failed trend request and keeps the heading and canvas mounted', async ({
    page,
    browserDiagnostics,
  }) => {
    const interceptedUrls: string[] = [];

    /*
     * Two records, both consequences of the status this test chose: Chrome's own network notice about
     * the non-ok response, and the subject's report of the rejection it caught. Nothing else the
     * browser says is tolerated, which is what makes "swallows" an assertion rather than a
     * description.
     */
    browserDiagnostics.allow(
      resourceFailure(TREND_REQUEST_FAILURE_STATUS),
      EXPECTED_TREND_FAILURE,
    );

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
        .poll(() => browserDiagnostics.errorText(), {
          message: `expected the subject to log the caught failure under ${TREND_FAILURE_LOG}`,
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toMatch(TREND_FAILURE_LOG);

      // The rejection was caught at L18-L20, so it never reached the page as an uncaught error.
      expect(browserDiagnostics.pageErrorText()).toBe('');
      await expect(container).toBeVisible();
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
    }
  });

  test('requests the trend series once per mount for the harness date range', async ({
    page,
    browserDiagnostics,
  }) => {
    const interceptedUrls: string[] = [];
    const interceptedMethods: string[] = [];

    // No forwarding header, so the well-formed fixture below still rejects, and that one caught
    // rejection is all this test permits.
    browserDiagnostics.allow(EXPECTED_TREND_FAILURE);

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
        .poll(() => browserDiagnostics.errorText(), {
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
    }
  });

  test('leaves the chart canvas out of the accessibility tree, with no name and no text alternative', async ({
    page,
    browserDiagnostics,
  }) => {
    const interceptedUrls: string[] = [];

    /*
     * The two records the rejection path below produces, declared for the same reason the first test
     * declares them: this test chose the failing status, and the subject's caught report of it
     * follows. An accessibility assertion is not exempt from the diagnostics verdict - it just has to
     * name the errors it caused, and the fixture attaches the whole ledger either way.
     */
    browserDiagnostics.allow(resourceFailure(TREND_REQUEST_FAILURE_STATUS), EXPECTED_TREND_FAILURE);

    // The rejection path. The markup this test reads is rendered unconditionally, so which trend
    // disposition applies is irrelevant - what matters is that the request is claimed.
    await page.route(TREND_REQUEST_GLOB, async (route) => {
      interceptedUrls.push(route.request().url());
      await route.fulfill({ status: TREND_REQUEST_FAILURE_STATUS, json: {} });
    });

    await page.goto(CHARTS_ROUTE);

    try {
      const canvas = page.locator(CHART_CANVAS);
      await expect(canvas).toBeAttached();

      /*
       * One read of every mechanism that could give the element a name or a role, plus its child
       * content. `null` is what `getAttribute` reports for an absent attribute, and an empty string
       * is the absence of the fallback content a canvas would otherwise carry. `id` is not a naming
       * mechanism: it is a hook for `document.getElementById`, nothing more.
       */
      const canvasNaming = await canvas.evaluate(
        (element: Element, attributes: readonly string[]) => ({
          attributes: Object.fromEntries(
            attributes.map((attribute) => [attribute, element.getAttribute(attribute)]),
          ),
          fallbackContent: element.innerHTML,
        }),
        [...CANVAS_NAMING_ATTRIBUTES],
      );

      expect(canvasNaming).toEqual({
        attributes: Object.fromEntries(
          CANVAS_NAMING_ATTRIBUTES.map((attribute) => [attribute, null]),
        ),
        fallbackContent: '',
      });

      // Chromium's own accessibility tree is the oracle: the canvas contributes no node to it.
      const accessibleNodes = await page.accessibility.snapshot({ interestingOnly: false });
      const roles = collectRoles(accessibleNodes);

      for (const role of CANVAS_CANDIDATE_ROLES) {
        expect(roles).not.toContain(role);
      }

      // What a screen reader is offered instead: the heading, and nothing of the series.
      expect(roles).toContain(HEADING_ROLE);
      await expect(page.locator(CHARTS_CONTAINER)).toHaveText(CHARTS_HEADING);
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
    }
  });

  test('does not paint a chart because Chart.register is never called', async ({
    page,
    browserDiagnostics,
  }) => {
    const interceptedUrls: string[] = [];

    /*
     * Two patterns, covering three records: Chart.js's report of the unregistered part, the uncaught
     * error React re-throws verbatim - so the same pattern matches it - and React's own report of the
     * unmount, which names the component. Neither pattern is keyed on the record's *kind*, so an
     * unrelated uncaught error in this test still fails it.
     */
    browserDiagnostics.allow(UNREGISTERED_CHART_PART, REPORTING_COMPONENT);

    // The forwarding header is what carries the subject past the L27 guard into `renderCharts`.
    // Without it the stub rejects a well-formed series, which is what tests 1 to 3 rely on.
    await page.route(TREND_REQUEST_GLOB, async (route) => {
      interceptedUrls.push(route.request().url());
      await route.fulfill({
        path: TRENDS_FIXTURE,
        contentType: 'application/json',
        headers: FORWARD_TREND_SERIES_HEADERS,
      });
    });

    await page.goto(CHARTS_ROUTE);

    try {
      // The registry L2's tree-shakeable import leaves empty is what L40 fails against.
      await expect
        .poll(() => browserDiagnostics.errorText(), {
          message: 'expected Chart.js to report a chart part that no module registered',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toMatch(UNREGISTERED_CHART_PART);

      // It escaped as an uncaught error, because `renderCharts` L32-L63 carries no try/catch and
      // the L26-L30 effect that calls it is passive - unlike the fetch at L16, which L18-L20 catch.
      expect(browserDiagnostics.pageErrorText()).toMatch(UNREGISTERED_CHART_PART);

      // React names the component the throw came out of, in a `console.error` it emits
      // after the uncaught error has already propagated, so this is polled rather than
      // read once.
      await expect
        .poll(() => browserDiagnostics.errorText(), {
          message: 'expected React to name the component the throw came out of',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toMatch(REPORTING_COMPONENT);

      /*
       * And it took the route with it: the heading and canvas L66-L69 rendered a moment earlier are
       * both gone, because nothing in the harness catches an error from a passive effect. Asserted
       * here rather than described in a skip reason.
       */
      await expect(page.locator(CHARTS_CONTAINER)).toHaveCount(0);
      await expect(page.locator(CHART_CANVAS)).toHaveCount(0);
      await expect(
        page.getByRole('heading', { level: CHARTS_HEADING_LEVEL, name: CHARTS_HEADING }),
      ).toHaveCount(0);

      // One request, so the unmount was the end of it rather than the start of a remount loop.
      expect(interceptedUrls).toHaveLength(1);
    } finally {
      await test.info().attach('intercepted-requests', {
        body: interceptedUrls.join('\n') || '(no request intercepted)',
        contentType: 'text/plain',
      });
    }
  });
});

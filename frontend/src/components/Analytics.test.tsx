/**
 * The suite for `frontend/src/components/Analytics`, whose single export is the default
 * `TrendCharts` - a component taking one required `dateRange` prop.
 *
 * Three properties of the subject shape every test below.
 *
 * 1. **The module is a file with no extension.** `frontend/jest.config.js` resolves the specifier
 *    `@/components/Analytics` to it through an explicit `moduleNameMapper` entry, and compiles it
 *    with the dedicated transformer in `frontend/jest.transform.extensionless.js`. That
 *    transformer's pattern is `$`-anchored, so this file - `Analytics.test.tsx` - is compiled by
 *    the primary ts-jest transform instead.
 *
 * 2. **`@/services/analyticsService` has no implementation.** Nothing under
 *    `frontend/src/services` provides it. `frontend/jest.config.js` maps the specifier to
 *    `frontend/src/test-utils/stubs/analyticsService.ts`, whose `getTrendData` always resolves
 *    with a non-falsy `{ labels, values }` and never throws. The `jest.mock` below replaces that
 *    stub with an automock; each test then installs the resolution or rejection it needs.
 *
 * 3. **Chart construction is reached but can never succeed.** The subject imports the
 *    tree-shakeable `{ Chart }` export of `chart.js` and never registers a controller or a scale,
 *    so a working chart is out of reach in every environment including a real browser.
 *
 * ## Three distinct paths through `renderCharts`, and one that is out of reach
 *
 * The subject's only `try`/`catch` wraps the `getTrendData` call at L16-L21. `renderCharts` and the
 * `new Chart(...)` inside it are **not** wrapped by anything, so "the failure is caught" is never a
 * correct description of a chart outcome here. Four outcomes exist and this file keeps them apart:
 *
 * | Path | What happens | Where it is asserted |
 * |------|--------------|----------------------|
 * | Controlled constructor | The `Chart` spy returns an inert instance. Nothing fails at all, and the subject writes nothing to `console.error` | the configuration, falsy-resolution and re-fetch cases |
 * | jsdom, real library | `chart.js` asks the canvas for a 2D context, jsdom has none, and the library **returns early of its own accord** rather than throwing. Nothing was caught: nothing was thrown | the "cannot acquire a canvas context" case |
 * | Fetch rejection | The L18-L20 `catch` runs, `chartData` stays `null`, and `renderCharts` is never entered - so no chart path is exercised at all. This is also the only path the E2E layer can reach, because the harness stub rejects on every route | the rejection case here, and `e2e/tests/analytics.spec.ts` |
 * | Real browser, real canvas | `_acquireContext` succeeds, the unregistered `'line'` controller raises, and because nothing wraps the effect the error propagates and React **unmounts** the subject | out of reach: no environment in this repository supplies a working canvas. Recorded as a ceiling, asserted nowhere |
 *
 * The fourth row is the ceiling. It is deliberately not simulated: forcing it would assert the
 * behaviour of a stand-in rather than of the subject.
 *
 * ## The Chart boundary is controlled
 *
 * `chart.js` is declared `^4.3.0` and no lockfile is committed, so the build a clean install
 * resolves is not fixed and neither is whatever diagnostic text that build emits. Its
 * `console.error` output is therefore never an oracle here. `beforeEach` instead spies on the
 * `Chart` export of the module registry - the same property the compiled subject reads at call
 * time - and substitutes an inert instance, which turns the chart assertions into assertions about
 * the subject's own behaviour: whether it constructs a chart at all, on which element, and with
 * which configuration. Under that substitution the subject writes nothing to `console.error`, and
 * this suite asserts exactly that.
 *
 * One case puts the real library back, by delegating through {@link ChartBeforeSpying}, and records
 * the ceiling with oracles that do not depend on the library's version: the constructor is entered
 * once, jsdom reports that it cannot supply a rendering context - which it does whatever `chart.js`
 * then makes of it, and `jest-environment-jsdom` is pinned exactly - nothing propagates, and the
 * component is still mounted with its canvas.
 *
 * This file installs no canvas or resize-observer shim and registers no Chart.js component; the
 * `Chart` spy is the only substitution, and it is created and restored per test.
 *
 * ## The canvas carries no accessible name - a documented ceiling
 *
 * L68 of the subject renders `<canvas id="trendChart"></canvas>` and nothing else: no `role`, no
 * `aria-label`, no `aria-labelledby`, no `title`, no fallback child content, and no adjacent table
 * or textual summary of the series. A canvas has no implicit ARIA role, so assistive technology is
 * offered nothing at all - the whole of the analytics content is unavailable to a screen reader, and
 * the `'Trend Charts'` heading is the only thing announced.
 *
 * That is the current behaviour and this suite pins it rather than papering over it. The last case
 * below asserts the absence of every naming mechanism, so adding one becomes a deliberate,
 * test-visible change. Supplying a name or a text alternative means editing
 * `frontend/src/components/Analytics`, which is production code this programme is not authorized to
 * change - the two authorized touches are both in `backend/`. It is recorded as a ceiling in
 * `frontend/TESTING.md`, `docs/testing/TRACEABILITY-MATRIX.md` §G and the suggested-next-tasks lists.
 *
 * @see frontend/src/components/Analytics - the module under test.
 * @see frontend/src/test-utils/stubs/analyticsService.ts - the mapped stub and its contract.
 * @see frontend/src/test-utils/render.tsx - `renderWithProviders`, the shared mount harness.
 * @see frontend/TESTING.md - the dual-transformer arrangement and the jsdom canvas pitfall.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this suite is shaped as
 *   it is, including which shims and mocks are not installed and why.
 */

import { act } from '@testing-library/react';

import TrendCharts from '@/components/Analytics';
import { getTrendData } from '@/services/analyticsService';
import { renderWithProviders } from '@/test-utils/render';

/*
 * Hoisted above the imports by the transform. Replaces the mapped stub named in item 2 of the
 * module docstring; `beforeEach` installs this suite's default resolution.
 */
jest.mock('@/services/analyticsService');

const getTrendDataMock = jest.mocked(getTrendData);

/*
 * The `chart.js` module object as it sits in this file's registry. The subject compiles to a
 * property read of this same object at the moment it constructs a chart, so a spy installed here is
 * the boundary the subject crosses. `require` rather than a namespace import: the interop helper an
 * `import * as` compiles to would hand back a copy, and a spy on a copy is a spy on nothing.
 */
// eslint-disable-next-line @typescript-eslint/no-var-requires
const chartModule = require('chart.js') as { Chart: unknown };

/**
 * The real `Chart` class, captured before any spy replaces the property.
 *
 * `jest.spyOn` cannot call an ES class constructor through - it applies the original as a plain
 * function, which throws `Class constructor Chart cannot be invoked without 'new'` - so the one case
 * that wants the real library constructs it explicitly through this reference.
 */
const ChartBeforeSpying = chartModule.Chart;

/**
 * The range every test renders with, held in one module-scope object whose identity is therefore
 * stable across renders. It is the dependency of the subject's fetch effect, and that effect re-runs
 * on a change of identity rather than of contents.
 */
const DATE_RANGE = { startDate: '2024-01-01', endDate: '2024-01-31' };

/** A second range, distinct from {@link DATE_RANGE} in both identity and contents. */
const OTHER_DATE_RANGE = { startDate: '2024-02-01', endDate: '2024-02-29' };

/**
 * The resolution `getTrendData` is given by default: non-falsy, so the subject's second effect
 * calls `renderCharts`, and carrying the only two members that function reads. Fixed literals -
 * nothing here is derived from the clock or from a random source.
 */
const TREND_SERIES = { labels: ['2024-01-01', '2024-01-02'], values: [1, 2] };

/**
 * The chart configuration the subject builds from {@link TREND_SERIES}, field for field as the
 * subject writes it. This is the whole of the second constructor argument, so a changed chart type,
 * a dataset wired to the wrong member of the fetched object, a dropped `responsive` flag or a
 * changed axis option is a difference here.
 */
const EXPECTED_CHART_CONFIGURATION = {
  type: 'line',
  data: {
    labels: TREND_SERIES.labels,
    datasets: [
      {
        label: 'Trend',
        data: TREND_SERIES.values,
        borderColor: 'rgb(75, 192, 192)',
        tension: 0.1,
      },
    ],
  },
  options: {
    responsive: true,
    scales: {
      y: {
        beginAtZero: true,
      },
    },
  },
};

/**
 * Fragment of the notice jsdom writes to `console.error` when a canvas is asked for a rendering
 * context it does not implement. It comes from `jest-environment-jsdom`, which
 * `frontend/package.json` pins exactly, so unlike anything `chart.js` emits it is reproducible.
 */
const CANVAS_CONTEXT_NOTICE_FRAGMENT = 'HTMLCanvasElement.prototype.getContext';

/** The canvas L68 of the subject renders. `id` is the only selector the subject provides. */
const CHART_CANVAS_SELECTOR = 'canvas#trendChart';

/**
 * Every attribute that could give the canvas an accessible name or put it in the accessibility
 * tree. The subject sets none of them; the accessibility case below asserts each absence
 * individually so the report names the one that appeared.
 */
const CANVAS_NAMING_ATTRIBUTES = [
  'role',
  'aria-label',
  'aria-labelledby',
  'aria-describedby',
  'title',
  'alt',
] as const;

/** Roles a named or role-bearing chart canvas would answer to. None is reachable today. */
const CANVAS_CANDIDATE_ROLES = ['img', 'figure', 'graphics-document'] as const;

/** The whole of the subject's rendered text: its heading, and nothing describing the series. */
const CHARTS_HEADING_TEXT = 'Trend Charts';

/** First of the two arguments the subject's `catch` block passes to `console.error`. */
const FETCH_FAILURE_PREFIX = 'Error fetching trend data:';

/** Message of the rejection installed by the rejection test below. */
const FETCH_REJECTION_MESSAGE = 'trend fetch failed';

/**
 * Fragment React logs when a state update lands outside `act`. The `afterEach` below asserts that
 * nothing recorded by the spy contains it.
 */
const ACT_WARNING_FRAGMENT = 'not wrapped in act';

let consoleError: jest.SpyInstance;
let chartConstructor: jest.SpyInstance;

/**
 * The inert object {@link chartConstructor} answers a construction with by default. Rebuilt per
 * test, and never read by the subject: it stores nothing and calls nothing back.
 */
let chartInstance: { destroy: jest.Mock };

/** Every `console.error` argument recorded so far, flattened to one string per call. */
function consoleErrorText(): string {
  return consoleError.mock.calls.map((args: unknown[]) => args.map(String).join(' ')).join('\n');
}

/**
 * Settles the promise `getTrendData` returned and applies the effects React schedules from the
 * state update that follows, all inside `act`.
 *
 * The subject fetches from an effect and stores the result in state, so a render is not complete
 * until that chain has run: the second effect - and with it `renderCharts` and the Chart.js call -
 * only runs on the render that the resolution triggers.
 */
async function flushFetchEffect(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('TrendCharts (src/components/Analytics)', () => {
  beforeEach(() => {
    getTrendDataMock.mockReset();
    getTrendDataMock.mockResolvedValue(TREND_SERIES);

    // Scoped to this suite and restored below. `frontend/src/test-utils/setup-jest.ts` leaves
    // `console` untouched, so this is the only spy on it while these tests run.
    consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    // The controlled Chart boundary. Answering with an inert object keeps every chart assertion
    // about what the subject asked for rather than about what the installed `chart.js` did with it.
    chartInstance = { destroy: jest.fn() };
    chartConstructor = jest
      .spyOn(chartModule, 'Chart' as never)
      .mockImplementation(() => chartInstance as never);
  });

  afterEach(() => {
    try {
      expect(consoleErrorText()).not.toContain(ACT_WARNING_FRAGMENT);
    } finally {
      chartConstructor.mockRestore();
      consoleError.mockRestore();
    }
  });

  it('renders the "Trend Charts" heading and the trendChart canvas', async () => {
    const { container, getByRole } = renderWithProviders(<TrendCharts dateRange={DATE_RANGE} />);

    await flushFetchEffect();

    expect(getByRole('heading', { level: 2, name: 'Trend Charts' })).toBeInTheDocument();

    // A canvas carries no accessible role, so it is reached through the DOM rather than a query.
    // The outer element has no class name; `id` is the only selector the subject provides.
    expect(container.querySelector('canvas#trendChart')).not.toBeNull();
  });

  it('calls getTrendData once, with the dateRange prop itself as its only argument', async () => {
    renderWithProviders(<TrendCharts dateRange={DATE_RANGE} />);

    await flushFetchEffect();

    expect(getTrendDataMock).toHaveBeenCalledTimes(1);
    expect(getTrendDataMock).toHaveBeenCalledWith(DATE_RANGE);

    // The prop is forwarded unaltered and unwrapped, so both its arity and its identity hold.
    expect(getTrendDataMock.mock.calls[0]).toHaveLength(1);
    expect(getTrendDataMock.mock.calls[0][0]).toBe(DATE_RANGE);
  });

  it('constructs one chart on the trendChart canvas with the configuration it owns', async () => {
    const { container } = renderWithProviders(<TrendCharts dateRange={DATE_RANGE} />);

    await flushFetchEffect();

    // The resolution was non-falsy, so the second effect's guard opened and `renderCharts` ran.
    expect(chartConstructor).toHaveBeenCalledTimes(1);

    const [element, configuration] = chartConstructor.mock.calls[0];

    // The element is the one the subject looked up by id, not merely some canvas.
    expect(element).toBe(container.querySelector('canvas#trendChart'));
    expect(configuration).toEqual(EXPECTED_CHART_CONFIGURATION);

    // The series reaches the chart as the very arrays the fetch resolved with: `labels` and
    // `values` are read straight off the stored object, so a swap between them is visible here.
    expect(configuration.data.labels).toBe(TREND_SERIES.labels);
    expect(configuration.data.datasets[0].data).toBe(TREND_SERIES.values);

    // Two arguments and no third: the subject passes no plugin list and no callback.
    expect(chartConstructor.mock.calls[0]).toHaveLength(2);

    // The subject itself reports nothing about charts. With the boundary controlled this is exact
    // rather than a count of whatever the installed `chart.js` chose to log.
    expect(consoleError).not.toHaveBeenCalled();
  });

  it('constructs no chart when getTrendData resolves with a falsy value', async () => {
    // `null` is the falsy resolution the second effect's guard exists for. The stub cannot produce
    // it, so this is the only route to the closed side of that branch.
    getTrendDataMock.mockResolvedValue(null as never);

    const { container, getByRole } = renderWithProviders(<TrendCharts dateRange={DATE_RANGE} />);

    await flushFetchEffect();

    expect(chartConstructor).not.toHaveBeenCalled();
    expect(consoleError).not.toHaveBeenCalled();

    // The markup does not depend on the fetch: heading and canvas are rendered unconditionally.
    expect(getByRole('heading', { level: 2, name: 'Trend Charts' })).toBeInTheDocument();
    expect(container.querySelector('canvas#trendChart')).not.toBeNull();
  });

  it('stays mounted because chart.js returns early when jsdom cannot supply a canvas context, not because anything caught a failure', async () => {
    // The one case that runs the installed `chart.js`. Its own diagnostic text and the number of
    // records it writes are deliberately not asserted: `chart.js` is a floating `^4.3.0` range with
    // no lockfile, so neither is reproducible across a clean install. What is asserted is the
    // subject's behaviour and jsdom's pinned notice.
    //
    // Note what this does NOT show. `renderCharts` is wrapped by no `try`/`catch`, so the subject
    // catches nothing here - `chart.js` fails to acquire a 2D context and returns of its own accord
    // before it reaches the unregistered `'line'` controller. In a real browser the context would be
    // acquired, the missing registration would raise, and with nothing wrapping the effect the error
    // would propagate and unmount the subject. That path is the ceiling in the module docstring and
    // is asserted nowhere.
    chartConstructor.mockImplementation(
      (...args: unknown[]) => new (ChartBeforeSpying as never)(...args),
    );

    const { container, getByRole } = renderWithProviders(<TrendCharts dateRange={DATE_RANGE} />);

    await flushFetchEffect();

    // The constructor was entered - the ceiling is inside the library, not before it.
    expect(chartConstructor).toHaveBeenCalledTimes(1);

    // jsdom implements no 2D context and says so as soon as the library asks for one. That request
    // is what a canvas-rendering library must make, so the notice is present for any version of it.
    expect(consoleErrorText()).toContain(CANVAS_CONTEXT_NOTICE_FRAGMENT);

    // Nothing propagated out of the effect: had the failure been thrown, React would have unmounted
    // the tree and neither query below would find its element.
    expect(getByRole('heading', { level: 2, name: 'Trend Charts' })).toBeInTheDocument();
    expect(container.querySelector('canvas#trendChart')).not.toBeNull();
  });

  it('swallows a getTrendData rejection, logs it, and never reaches renderCharts', async () => {
    const rejection = new Error(FETCH_REJECTION_MESSAGE);

    getTrendDataMock.mockRejectedValue(rejection);

    const { container, getByRole } = renderWithProviders(<TrendCharts dateRange={DATE_RANGE} />);

    await flushFetchEffect();

    // The rejection is caught and logged; it is not re-thrown and no replacement error is raised.
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith(FETCH_FAILURE_PREFIX, expect.any(Error));

    const loggedArguments = consoleError.mock.calls[0];

    expect(loggedArguments).toHaveLength(2);
    expect(loggedArguments[0]).toBe(FETCH_FAILURE_PREFIX);
    expect(loggedArguments[1]).toBe(rejection);
    expect(loggedArguments[1].message).toBe(FETCH_REJECTION_MESSAGE);

    // No chart was attempted: the stored data stayed null, so the second effect's guard did not
    // open and `renderCharts` was never entered. Read at the boundary itself rather than inferred
    // from an absent log line.
    expect(chartConstructor).not.toHaveBeenCalled();

    expect(getByRole('heading', { level: 2, name: 'Trend Charts' })).toBeInTheDocument();
    expect(container.querySelector('canvas#trendChart')).not.toBeNull();
  });

  it('does not refetch when the same dateRange object is passed again', async () => {
    const { rerender } = renderWithProviders(<TrendCharts dateRange={DATE_RANGE} />);

    await flushFetchEffect();
    expect(getTrendDataMock).toHaveBeenCalledTimes(1);

    rerender(<TrendCharts dateRange={DATE_RANGE} />);
    await flushFetchEffect();

    // The fetch effect depends on the prop's identity, which this re-render did not change.
    expect(getTrendDataMock).toHaveBeenCalledTimes(1);
  });

  it('refetches with the new object when the dateRange prop changes identity', async () => {
    const { rerender } = renderWithProviders(<TrendCharts dateRange={DATE_RANGE} />);

    await flushFetchEffect();
    expect(getTrendDataMock).toHaveBeenCalledTimes(1);

    rerender(<TrendCharts dateRange={OTHER_DATE_RANGE} />);
    await flushFetchEffect();

    expect(getTrendDataMock).toHaveBeenCalledTimes(2);
    expect(getTrendDataMock.mock.calls[1]).toHaveLength(1);
    expect(getTrendDataMock.mock.calls[1][0]).toBe(OTHER_DATE_RANGE);
  });

  it('offers assistive technology no name, role or text alternative for the chart canvas', async () => {
    const { container, getByRole, queryByRole } = renderWithProviders(
      <TrendCharts dateRange={DATE_RANGE} />,
    );

    await flushFetchEffect();

    const canvas = container.querySelector(CHART_CANVAS_SELECTOR);

    expect(canvas).not.toBeNull();

    // Every mechanism that could put this element in the accessibility tree with a name, absent.
    // `id` is not one of them: it is a hook for `document.getElementById`, nothing more.
    for (const attribute of CANVAS_NAMING_ATTRIBUTES) {
      expect(canvas).not.toHaveAttribute(attribute);
    }

    // No fallback content either, which is the other way a canvas carries an alternative.
    expect(canvas).toBeEmptyDOMElement();

    // A canvas has no implicit role, and nothing above supplied one, so no role query reaches it.
    for (const role of CANVAS_CANDIDATE_ROLES) {
      expect(queryByRole(role)).toBeNull();
    }

    // What is left for a screen reader is the heading, and nothing of the series itself: no table,
    // no list, and no textual summary anywhere in the subtree.
    expect(getByRole('heading', { level: 2, name: 'Trend Charts' })).toBeInTheDocument();
    expect(queryByRole('table')).toBeNull();
    expect(queryByRole('list')).toBeNull();
    expect(container.textContent).toBe(CHARTS_HEADING_TEXT);
  });
});

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
 * 3. **Chart construction always fails, and that is the behaviour asserted here.** The subject
 *    imports the tree-shakeable `{ Chart }` export of `chart.js` and never registers a controller
 *    or a scale, and jsdom implements no 2D canvas context. Two `console.error` records follow, in
 *    this order: jsdom reports {@link CANVAS_NOT_IMPLEMENTED_MESSAGE} as an `Error`, and returns no
 *    context; Chart.js, unable to acquire one, reports {@link CHART_FAILURE_MESSAGE} as a string
 *    and returns from its constructor, before it would reach a controller or scale lookup. Nothing
 *    is thrown, so the component stays mounted. This is a permanent ceiling of the implemented
 *    code: the absent registration puts the branch out of reach in a real browser too.
 *
 * This file installs no canvas or resize-observer shim, substitutes nothing for `chart.js`, and
 * registers no Chart.js component: Chart.js runs unmodified against jsdom. `console.error` is
 * spied on per test and restored, and each test asserts on what it recorded - jsdom's
 * not-implemented notice, Chart.js's report, and the subject's own fetch-failure log.
 *
 * @see frontend/src/components/Analytics - the module under test.
 * @see frontend/src/test-utils/stubs/analyticsService.ts - the mapped stub and its contract.
 * @see frontend/src/test-utils/render.tsx - `renderWithProviders`, the shared mount harness.
 * @see frontend/TESTING.md - the dual-transformer arrangement and the jsdom canvas pitfall.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this suite is shaped as
 *   it is, including the shims and mocks deliberately not used.
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
 * Message of the `Error` jsdom reports, as the sole `console.error` argument, when a canvas is asked
 * for a rendering context. jsdom returns no context, which is what Chart.js then fails on.
 */
const CANVAS_NOT_IMPLEMENTED_MESSAGE =
  'Not implemented: HTMLCanvasElement.prototype.getContext (without installing the canvas npm package)';

/**
 * Emitted by the Chart.js constructor, as its sole `console.error` argument, when it cannot acquire
 * a 2D context. Verbatim from `chart.js` 4.5.1.
 */
const CHART_FAILURE_MESSAGE = "Failed to create chart: can't acquire context from the given item";

/** Number of `console.error` records one failed chart construction produces: the two in item 3. */
const CHART_FAILURE_LOG_COUNT = 2;

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
  });

  afterEach(() => {
    try {
      expect(consoleErrorText()).not.toContain(ACT_WARNING_FRAGMENT);
    } finally {
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

  it('reports Chart.js failing to acquire a canvas context, and stays mounted', async () => {
    const { container, getByRole } = renderWithProviders(<TrendCharts dateRange={DATE_RANGE} />);

    await flushFetchEffect();

    // The default resolution is non-falsy, so the second effect's guard held, `renderCharts` ran,
    // the canvas lookup found the element, and `new Chart(...)` was reached.
    expect(consoleError).toHaveBeenCalledTimes(CHART_FAILURE_LOG_COUNT);

    // The cause first: jsdom has no rendering context to give, and says so as an Error.
    expect(String(consoleError.mock.calls[0][0])).toContain(CANVAS_NOT_IMPLEMENTED_MESSAGE);

    // Then the consequence: Chart.js reports the failure as its only argument and returns.
    expect(consoleError.mock.calls[1]).toHaveLength(1);
    expect(consoleError.mock.calls[1][0]).toBe(CHART_FAILURE_MESSAGE);
    expect(consoleErrorText()).toContain(CHART_FAILURE_MESSAGE);

    // Nothing propagated out of the effect - the count above admits no React error report - so the
    // subject is still on the page with its canvas.
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
    // open and `renderCharts` was never entered. Both records a chart attempt always produces are
    // absent - the canvas was never asked for a context, and Chart.js reported nothing.
    expect(consoleErrorText()).not.toContain(CANVAS_NOT_IMPLEMENTED_MESSAGE);
    expect(consoleErrorText()).not.toContain(CHART_FAILURE_MESSAGE);

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
});

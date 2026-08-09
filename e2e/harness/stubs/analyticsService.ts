/**
 * Harness stand-in for the specifier `@/services/analyticsService`, which
 * `frontend/src/components/Analytics` imports and `frontend/src/services/` does not
 * provide. `e2e/vite.harness.config.ts` redirects that specifier here while that
 * remains true.
 *
 * Reads its data over HTTP from {@link TRENDS_ENDPOINT}. That path and the `start`
 * and `end` query parameter names are the contract the end-to-end specs intercept,
 * fulfilling from `e2e/fixtures/trends.json`.
 *
 * Contract this module guarantees to every spec. `getTrendData` **resolves on exactly one
 * path and rejects on every other**, and the response a spec fulfils with is what selects
 * between them:
 *
 * 1. It checks the response status, then parses the body. The body is read to completion
 *    on both paths.
 * 2. A parsed body that is not a {@link TrendSeries} rejects with
 *    {@link TrendSeriesContractError}, which names the member at fault.
 * 3. A parsed body that *is* a {@link TrendSeries} rejects with
 *    {@link UnrenderableTrendSeriesError} - **unless** the response carries
 *    {@link FORWARD_TREND_SERIES_HEADER}, in which case it **resolves** with that series.
 *
 * So refusal is the default, the three rejections are distinguishable by type, and a spec
 * opts into the resolving path by setting that header. Doing so carries the subject into
 * `renderCharts`, whose `new Chart(...)` throws out of a passive effect and unmounts the
 * route, so the opt-in is what makes the chart ceiling assertable and why refusal is the
 * default.
 *
 * @see docs/testing/DECISION-LOG.md - row D127, which refines D44.
 * @see docs/testing/DECISION-LOG.md - row D143, the non-ok body read.
 * @see docs/testing/DECISION-LOG.md - rows D231 and D346, the opt-in forwarding header.
 * @see docs/testing/TRACEABILITY-MATRIX.md - the unreachable chart branch as an
 *   assertion obligation.
 */

interface DateRange {
  startDate: string;
  endDate: string;
}

/**
 * Series shape the caller reads: `frontend/src/components/Analytics` passes `labels`
 * to Chart.js as the dataset labels at line 43 and `values` as its data at line 47.
 * It is also the shape of `e2e/fixtures/trends.json`.
 */
export interface TrendSeries {
  labels: string[];
  values: number[];
}

/** Endpoint the specs intercept, and the only place this path is written. */
const TRENDS_ENDPOINT = '/api/trends';

/**
 * Response header a spec sets to have a well-formed series forwarded to the caller
 * instead of rejected.
 *
 * Read same-origin, so no CORS filtering hides it. Absent from every response the
 * harness dev server itself produces - it answers an unintercepted `/api/trends` with
 * `503 harness-api-not-intercepted` - so the forwarding path is reachable only from a
 * spec that asks for it by name.
 */
export const FORWARD_TREND_SERIES_HEADER = 'x-harness-forward-trend-series';

/**
 * The one value {@link FORWARD_TREND_SERIES_HEADER} is honoured for.
 *
 * Compared exactly, so a header carrying anything else - including `'0'`, `'false'` or
 * an empty string - leaves the default rejection in place rather than half-enabling a
 * path that unmounts the route.
 */
export const FORWARD_TREND_SERIES_VALUE = '1';

/**
 * Rejection produced when the fetched body is not a {@link TrendSeries}.
 *
 * Distinct from {@link UnrenderableTrendSeriesError}: this one means the payload a
 * spec supplied, or `e2e/fixtures/trends.json` itself, does not match the declared
 * shape, so no conclusion about the component can be drawn from the run.
 */
export class TrendSeriesContractError extends Error {
  /** Request URL the body was read from. */
  readonly url: string;

  /** The single member at fault, as {@link describeTrendSeriesViolation} reports it. */
  readonly violation: string;

  constructor(url: string, violation: string) {
    super(
      `GET ${url} returned a body that is not a trend series: ${violation}. ` +
        'The payload a spec fulfils this route with, or e2e/fixtures/trends.json, ' +
        'must carry a "labels" array of string and a "values" array of finite number.',
    );
    this.name = 'TrendSeriesContractError';
    this.url = url;
    this.violation = violation;
  }
}

/**
 * Rejection produced for a well-formed {@link TrendSeries} the response did not opt into
 * forwarding.
 *
 * Named so a spec, or a page-error listener, can attribute the console line the
 * component logs. `frontend/src/components/Analytics` catches it at lines 18-20,
 * leaves its `chartData` state `null` and never reaches `renderCharts`, so the
 * `/analytics` route renders `<h2>Trend Charts</h2>` and `<canvas id="trendChart">`.
 */
export class UnrenderableTrendSeriesError extends Error {
  /** Request URL the series was read from. */
  readonly url: string;

  /** Number of labels the series carried. */
  readonly labelCount: number;

  constructor(url: string, series: TrendSeries) {
    super(
      `GET ${url} returned a trend series of ${series.labels.length} labels, which this ` +
        'response did not opt into forwarding: @/components/Analytics constructs a Chart ' +
        'from the tree-shakeable { Chart } export without calling Chart.register, so a ' +
        'renderable series throws out of its useEffect and unmounts the route. Most specs ' +
        `assert the caught-failure path instead; one that asserts that unmount sets the ` +
        `"${FORWARD_TREND_SERIES_HEADER}" response header.`,
    );
    this.name = 'UnrenderableTrendSeriesError';
    this.url = url;
    this.labelCount = series.labels.length;
  }
}

/**
 * Reports why `payload` is not a {@link TrendSeries}, or `null` when it is one.
 *
 * Both members must be present, must be arrays, and must hold only `string` and only
 * finite `number` respectively.
 *
 * @param payload - Parsed response body.
 * @returns The first violation found, naming the member and the value, or `null`.
 */
function describeTrendSeriesViolation(payload: unknown): string | null {
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    return `expected an object, received ${JSON.stringify(payload)}`;
  }

  const candidate = payload as Partial<TrendSeries>;

  if (!Array.isArray(candidate.labels)) {
    return `"labels" is ${JSON.stringify(candidate.labels)}, expected an array of string`;
  }
  const badLabel = candidate.labels.findIndex((label) => typeof label !== 'string');
  if (badLabel !== -1) {
    return `"labels[${badLabel}]" is ${JSON.stringify(candidate.labels[badLabel])}, expected a string`;
  }

  if (!Array.isArray(candidate.values)) {
    return `"values" is ${JSON.stringify(candidate.values)}, expected an array of number`;
  }
  const badValue = candidate.values.findIndex(
    (value) => typeof value !== 'number' || !Number.isFinite(value),
  );
  if (badValue !== -1) {
    return `"values[${badValue}]" is ${JSON.stringify(candidate.values[badValue])}, expected a finite number`;
  }

  return null;
}

/**
 * Requests the trend series covering one date range, then resolves with it only if the
 * response opted in with {@link FORWARD_TREND_SERIES_HEADER}, and otherwise rejects.
 *
 * Called by `frontend/src/components/Analytics` with a single argument carrying the whole
 * range object.
 *
 * @param dateRange - Range whose two members become the `start` and `end` query
 *   parameters, interpolated verbatim.
 * @returns The fetched series, on the one path where the response carried
 *   {@link FORWARD_TREND_SERIES_HEADER}.
 * @throws Error - When the response status falls outside 200-299. The body is read to
 *   completion and discarded first; the message names the request URL and that status,
 *   and carries nothing the body held.
 * @throws TrendSeriesContractError - When the parsed body is not a
 *   {@link TrendSeries}. Checked before the opt-in, so opting in cannot smuggle a
 *   malformed payload past the shape check.
 * @throws UnrenderableTrendSeriesError - When it is one and the response did not opt in.
 */
export const getTrendData = async (dateRange: DateRange): Promise<TrendSeries> => {
  const url = `${TRENDS_ENDPOINT}?start=${dateRange.startDate}&end=${dateRange.endDate}`;

  const response = await fetch(url);

  if (!response.ok) {
    // Drains the body and discards it (D143). The status error below is thrown either way.
    await response.text().catch(() => undefined);
    throw new Error(`GET ${url} failed with HTTP status ${response.status}`);
  }

  const payload: unknown = await response.json();

  const violation = describeTrendSeriesViolation(payload);
  if (violation !== null) {
    throw new TrendSeriesContractError(url, violation);
  }

  const series = payload as TrendSeries;

  if (response.headers.get(FORWARD_TREND_SERIES_HEADER) === FORWARD_TREND_SERIES_VALUE) {
    // The one resolving path, reached only when the response opted in by name.
    return series;
  }

  throw new UnrenderableTrendSeriesError(url, series);
};

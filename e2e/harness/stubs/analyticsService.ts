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
 * Contract this module guarantees to every spec:
 *
 * 1. `getTrendData` checks the response status, then parses the body. Either way the
 *    body is read to completion, so the response is never left with an open stream.
 * 2. A parsed body that is not a {@link TrendSeries} rejects with
 *    {@link TrendSeriesContractError}, which names the member at fault.
 * 3. A parsed body that *is* a {@link TrendSeries} rejects with
 *    {@link UnrenderableTrendSeriesError}.
 *
 * So it always rejects, but the three rejections are distinguishable: a fixture
 * that has drifted from the declared shape is reported as a contract failure rather
 * than absorbed into the intentional refusal at step 3.
 *
 * @see docs/testing/DECISION-LOG.md - row D127, which refines D44.
 * @see docs/testing/DECISION-LOG.md - row D143, the non-ok body read.
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
 * Rejection produced for a well-formed {@link TrendSeries}.
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
      `GET ${url} returned a trend series of ${series.labels.length} labels, which the ` +
        'harness does not forward: @/components/Analytics constructs a Chart from the ' +
        'tree-shakeable { Chart } export without calling Chart.register, so a renderable ' +
        'series throws out of its useEffect and unmounts the route. The route is asserted ' +
        'on its caught-failure path instead.',
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
 * Requests the trend series covering one date range, then rejects.
 *
 * Called as `getTrendData(dateRange)` at line 16 of
 * `frontend/src/components/Analytics` - a single argument carrying the whole range
 * object.
 *
 * @param dateRange - Range whose two members become the `start` and `end` query
 *   parameters, interpolated verbatim.
 * @returns Never resolves.
 * @throws Error - When the response status falls outside 200-299. The body is read to
 *   completion and discarded first, so the message names the request URL and that
 *   status and carries nothing the body held.
 * @throws TrendSeriesContractError - When the parsed body is not a
 *   {@link TrendSeries}.
 * @throws UnrenderableTrendSeriesError - When it is one.
 */
export const getTrendData = async (dateRange: DateRange): Promise<TrendSeries> => {
  const url = `${TRENDS_ENDPOINT}?start=${dateRange.startDate}&end=${dateRange.endDate}`;

  const response = await fetch(url);

  if (!response.ok) {
    // Drains the body and discards it; a read failure here changes nothing that follows.
    await response.text().catch(() => undefined);
    throw new Error(`GET ${url} failed with HTTP status ${response.status}`);
  }

  const payload: unknown = await response.json();

  const violation = describeTrendSeriesViolation(payload);
  if (violation !== null) {
    throw new TrendSeriesContractError(url, violation);
  }

  throw new UnrenderableTrendSeriesError(url, payload as TrendSeries);
};

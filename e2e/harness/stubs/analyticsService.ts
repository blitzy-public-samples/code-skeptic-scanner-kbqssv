/**
 * Harness stand-in for the specifier `@/services/analyticsService`, which
 * `frontend/src/components/Analytics` imports and `frontend/src/services/` does not
 * provide. `e2e/vite.harness.config.ts` redirects that specifier here.
 *
 * `frontend/src/services/` ships only `api.ts`, `llmService.ts` and
 * `twitterService.ts`, so the specifier that `frontend/src/components/Analytics`
 * imports at line 3 has no implementation in the repository. The resolver in
 * `e2e/vite.harness.config.ts` redirects it here while that remains true.
 *
 * Reads its data over HTTP from the `/api/trends` endpoint. The endpoint path and
 * the `start` and `end` query parameter names are the contract the end-to-end
 * specs intercept, answering from `e2e/fixtures/trends.json`.
 *
 * Contract this module guarantees to every spec: `getTrendData` ALWAYS rejects,
 * and it rejects only after the response status has been checked and the body
 * parsed. `frontend/src/components/Analytics` catches that rejection at lines
 * 18-20, leaves its `chartData` state `null`, and therefore never reaches
 * `renderCharts`, so the `/analytics` route renders `<h2>Trend Charts</h2>` and
 * `<canvas id="trendChart">` for every payload a spec supplies. Handing the
 * component a renderable series instead makes it construct a `Chart` from the
 * tree-shakeable `{ Chart }` export with nothing registered, which throws out of
 * a `useEffect` and unmounts the whole route.
 *
 * @see docs/testing/DECISION-LOG.md - section 4, this refusal and the alternatives to it.
 * @see docs/testing/TRACEABILITY-MATRIX.md - the unreachable chart branch as an
 *   assertion obligation.
 */

interface DateRange {
  startDate: string;
  endDate: string;
}

/** Shape `frontend/src/components/Analytics` reads off a resolved trend series. */
interface TrendSeries {
  labels: unknown;
  values: unknown;
}

/**
 * Rejection `getTrendData` always produces once the fixture has been fetched and
 * parsed. Named so a spec, or a page-error listener, can attribute the console
 * line the component logs.
 */
export class UnrenderableTrendSeriesError extends Error {
  /** Request URL the series was read from. */
  readonly url: string;

  /** Number of labels the fixture carried, or `-1` when it carried no array. */
  readonly labelCount: number;

  constructor(url: string, series: TrendSeries) {
    const labelCount = Array.isArray(series.labels) ? series.labels.length : -1;
    super(
      `GET ${url} returned a trend series of ${labelCount} labels, which the harness ` +
        'does not forward: @/components/Analytics constructs a Chart from the ' +
        'tree-shakeable { Chart } export without calling Chart.register, so a renderable ' +
        'series throws out of its useEffect and unmounts the route. The route is asserted ' +
        'on its caught-failure path instead.',
    );
    this.name = 'UnrenderableTrendSeriesError';
    this.url = url;
    this.labelCount = labelCount;
  }
}

/**
 * Series shape the caller reads: `frontend/src/components/Analytics` passes
 * `labels` to Chart.js as the dataset labels at line 43 and `values` as its data
 * at line 47. It is also the shape of `e2e/fixtures/trends.json`.
 */
export interface TrendSeries {
  labels: string[];
  values: number[];
}

/** Endpoint the specs intercept. */
const TRENDS_ENDPOINT = '/api/trends';

/**
 * Reports why `payload` is not a {@link TrendSeries}, or `null` when it is one.
 *
 * Both members must be present, must be arrays, and must hold only `string` and
 * only finite `number` respectively, so a fixture that drifts from the declared
 * shape is named rather than passed on as `any`.
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
 * @throws Error - When the response status falls outside 200-299. The message
 *   names the request URL and that status.
 * @throws UnrenderableTrendSeriesError - Once the body has been parsed, on every
 *   successful response.
 */
export const getTrendData = async (dateRange: DateRange): Promise<TrendSeries> => {
  const url = `/api/trends?start=${dateRange.startDate}&end=${dateRange.endDate}`;

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`GET ${url} failed with HTTP status ${response.status}`);
  }

  // The body is parsed, so a malformed fixture surfaces as a parse failure here
  // rather than being masked by the refusal below.
  const series = (await response.json()) as TrendSeries;

  throw new UnrenderableTrendSeriesError(url, series);
};

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
 *    on both paths, and on the non-ok path a bounded excerpt of it travels in the message
 *    of the error thrown, so a server-supplied reason reaches the caller's console rather
 *    than being discarded.
 * 2. A parsed body that is not a {@link TrendSeries} rejects with
 *    {@link TrendSeriesContractError}, which names the member at fault. A `labels` and a
 *    `values` array of *different lengths* is one such body: the two members are read in
 *    parallel by the caller, so a series that pairs 6 labels with 3 values is not a series,
 *    and it is refused here rather than forwarded into a chart that cannot report it.
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
 * @see docs/testing/DECISION-LOG.md - row D143, the non-ok body read, and row D394, which
 *   carries what that read produced into the thrown message.
 * @see docs/testing/DECISION-LOG.md - row D395, the length-agreement check.
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
 * path that unmounts the whole React root.
 */
export const FORWARD_TREND_SERIES_VALUE = '1';

/**
 * Longest response-body excerpt a status error carries.
 *
 * Bounded so that an error page, a stack trace or a large payload answered by mistake
 * cannot turn one console line into a wall of text. Every reason this harness's own
 * responders produce - the `503 harness-api-not-intercepted` document, and the small JSON
 * objects a spec fulfils a failing route with - fits inside it whole.
 */
const BODY_EXCERPT_LIMIT = 300;

/** Excerpt used when the response carried no body at all. */
const EMPTY_BODY_EXCERPT = '(no body)';

/** Excerpt used when reading the body itself failed, which the caller never sees as a rejection. */
const UNREADABLE_BODY_EXCERPT = '(body could not be read)';

/**
 * Reduces a response body to one bounded, single-line excerpt fit for an error message.
 *
 * Whitespace is collapsed so a pretty-printed JSON body stays on the single console line the
 * caller logs it on, and the result is truncated to {@link BODY_EXCERPT_LIMIT} with the full
 * length stated, so a reader can tell a short reason from a truncated one.
 *
 * @param body - Response body, read to completion.
 * @returns The excerpt, or {@link EMPTY_BODY_EXCERPT} when the body held nothing but whitespace.
 */
function excerptResponseBody(body: string): string {
  const collapsed = body.replace(/\s+/g, ' ').trim();

  if (collapsed === '') {
    return EMPTY_BODY_EXCERPT;
  }

  if (collapsed.length <= BODY_EXCERPT_LIMIT) {
    return collapsed;
  }

  return `${collapsed.slice(0, BODY_EXCERPT_LIMIT)}... (${collapsed.length} characters in total)`;
}

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
 *
 * Rejecting is therefore the *containing* outcome, and forwarding is the destructive one:
 * see {@link FORWARD_TREND_SERIES_HEADER} for what a forwarded series costs.
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
        'renderable series throws out of its useEffect, and with no error boundary anywhere ' +
        'above it that throw unmounts the whole React root - the Provider, the Router and the ' +
        'landmark with it, leaving #root empty and no route reachable until a reload. Most ' +
        `specs assert the caught-failure path instead; one that asserts that teardown sets ` +
        `the "${FORWARD_TREND_SERIES_HEADER}" response header.`,
    );
    this.name = 'UnrenderableTrendSeriesError';
    this.url = url;
    this.labelCount = series.labels.length;
  }
}

/**
 * Reports why `payload` is not a {@link TrendSeries}, or `null` when it is one.
 *
 * Both members must be present, must be arrays, must hold only `string` and only
 * finite `number` respectively, and must carry the **same number of entries**.
 *
 * The length agreement is a member of this contract because the caller reads the two arrays in
 * parallel - `frontend/src/components/Analytics` passes `labels` as the chart's labels and
 * `values` as its data - so a payload pairing 6 labels with 3 values describes no series at all.
 * It is checked ahead of {@link FORWARD_TREND_SERIES_HEADER}, so opting into forwarding cannot
 * carry such a payload past this function. See `docs/testing/DECISION-LOG.md` row D395.
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

  if (candidate.labels.length !== candidate.values.length) {
    return (
      `"labels" carries ${candidate.labels.length} ${pluralEntries(candidate.labels.length)} ` +
      `and "values" carries ${candidate.values.length}, expected the same number of each`
    );
  }

  return null;
}

/**
 * The word that follows a count of array members, so a violation message reads as prose.
 *
 * @param count - Number of members.
 * @returns `'entry'` for exactly one, `'entries'` otherwise.
 */
function pluralEntries(count: number): string {
  return count === 1 ? 'entry' : 'entries';
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
 *   completion first, and the message names the request URL, that status and a bounded
 *   excerpt of that body - so a reason the responder supplied, such as this harness's own
 *   `harness-api-not-intercepted` remedy, reaches the caller's console instead of being
 *   discarded. The body is never parsed and never becomes a return value, so the status
 *   error still wins over any body-derived outcome.
 * @throws TrendSeriesContractError - When the parsed body is not a
 *   {@link TrendSeries}, which includes `labels` and `values` of unequal length. Checked
 *   before the opt-in, so opting in cannot smuggle a malformed payload past the shape check.
 * @throws UnrenderableTrendSeriesError - When it is one and the response did not opt in.
 */
export const getTrendData = async (dateRange: DateRange): Promise<TrendSeries> => {
  const url = `${TRENDS_ENDPOINT}?start=${dateRange.startDate}&end=${dateRange.endDate}`;

  const response = await fetch(url);

  if (!response.ok) {
    /*
     * Drains the body (D143), then carries a bounded excerpt of it into the message (D394).
     * The read is still what makes the request visible to the resource timeline and its body
     * retrievable from the debugger; what changed is that the reason it holds is no longer
     * thrown away. A read failure yields a fixed excerpt rather than a rejection of its own,
     * so the status error below is thrown on every path either way.
     */
    const excerpt = await response
      .text()
      .then(excerptResponseBody)
      .catch(() => UNREADABLE_BODY_EXCERPT);

    throw new Error(
      `GET ${url} failed with HTTP status ${response.status}. Response body: ${excerpt}`,
    );
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

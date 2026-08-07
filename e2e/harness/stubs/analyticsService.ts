/**
 * Harness stand-in for the module specifier `@/services/analyticsService`.
 *
 * `frontend/src/services/` ships only `api.ts`, `llmService.ts` and
 * `twitterService.ts`, so the specifier that `frontend/src/components/Analytics`
 * imports at line 3 has no implementation in the repository. The resolver in
 * `e2e/vite.harness.config.ts` redirects it here while that remains true.
 *
 * Reads its data over HTTP from the `/api/trends` endpoint. The endpoint path and
 * the `start` and `end` query parameter names are the contract the end-to-end
 * specs intercept, answering from `e2e/fixtures/trends.json`.
 */

/**
 * Structural equivalent of the `DateRange` interface declared at lines 5-8 of
 * `frontend/src/components/Analytics`. That declaration is local to the component
 * module and carries no `export`.
 */
interface DateRange {
  startDate: string;
  endDate: string;
}

/**
 * Requests the trend series covering one date range.
 *
 * Called as `getTrendData(dateRange)` at line 16 of
 * `frontend/src/components/Analytics` - a single argument carrying the whole range
 * object. The caller reads `labels` and `values` off the resolved value and hands
 * them to Chart.js as the line dataset's labels (line 43) and data (line 47).
 *
 * @param dateRange - Range whose two members become the `start` and `end` query
 *   parameters, interpolated verbatim.
 * @returns The parsed response body, exactly as received.
 * @throws Error - When the response status falls outside 200-299. The message
 *   names the request URL and that status.
 */
export const getTrendData = async (dateRange: DateRange): Promise<any> => {
  const url = `/api/trends?start=${dateRange.startDate}&end=${dateRange.endDate}`;

  const response = await fetch(url);

  // Marker: the status is read before the body.
  if (!response.ok) {
    throw new Error(`GET ${url} failed with HTTP status ${response.status}`);
  }

  return await response.json();
};

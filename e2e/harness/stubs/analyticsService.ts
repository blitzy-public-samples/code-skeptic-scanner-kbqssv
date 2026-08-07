/**
 * Harness stand-in for the module specifier `@/services/analyticsService`.
 *
 * `frontend/src/services/` ships only `api.ts`, `llmService.ts` and
 * `twitterService.ts`, so the specifier that `frontend/src/components/Analytics`
 * imports at line 3 has no implementation in the repository. The resolver in
 * `e2e/vite.harness.config.ts` redirects it here while that remains true.
 *
 * Resolves with static data and performs no network, timer or clock work, so
 * every call yields the same values on every run.
 */

/**
 * Structural equivalent of the `DateRange` interface declared at lines 5-8 of
 * `frontend/src/components/Analytics`. That declaration is local to the component
 * module and carries no `export`, so it cannot be imported.
 */
export interface DateRange {
  startDate: string;
  endDate: string;
}

/**
 * Shape returned by {@link getTrendData}. `labels` and `values` are the only two
 * members the component reads: it passes them to Chart.js as the line dataset's
 * labels (line 43) and data (line 47).
 */
export interface TrendSeries {
  labels: string[];
  values: number[];
}

/**
 * Called as `getTrendData(dateRange)` at line 16 of
 * `frontend/src/components/Analytics` - a single argument carrying the whole
 * range object.
 *
 * The argument is deliberately unread so that a spy records the caller's own
 * object exactly as the caller passed it. A fresh result, including fresh nested
 * arrays, is allocated on every call.
 */
export async function getTrendData(dateRange: DateRange): Promise<TrendSeries> {
  void dateRange;
  return {
    labels: ['2024-01-01', '2024-01-02', '2024-01-03'],
    values: [4, 9, 6],
  };
}

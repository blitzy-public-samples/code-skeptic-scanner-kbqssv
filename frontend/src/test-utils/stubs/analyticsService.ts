/**
 * Test-side implementation of the module specifier `@/services/analyticsService`.
 *
 * `frontend/src/services/` ships only `api.ts`, `llmService.ts` and
 * `twitterService.ts`, so `@/services/analyticsService` has no implementation in
 * the repository. Under Jest the specifier resolves to this file through the
 * `moduleNameMapper` entry in `frontend/jest.config.js`, which is listed with
 * every other mapper group in `frontend/TESTING.md`.
 *
 * The two consuming call sites fix the two signatures below.
 *
 * `frontend/src/components/Analytics` imports `getTrendData` at line 3 and calls
 * it at line 16 as `getTrendData(dateRange)` - a single argument carrying the
 * whole `{ startDate, endDate }` object described by the component's own
 * `DateRange` interface at lines 5-8. The resolved value is read only as
 * `chartData.labels` (line 43) and `chartData.values` (line 47).
 *
 * `frontend/src/pages/Analytics.tsx` imports `getAnalyticsData` at line 3 and
 * calls it at line 18 as
 * `getAnalyticsData(dateRange.start, dateRange.end, user.id)` - three arguments.
 * The resolved value is read as `analyticsData.trends`,
 * `analyticsData.aiToolComparison` and `analyticsData.userEngagement` (lines
 * 39-41), and is non-falsy so that the `if (!analyticsData)` guard at lines
 * 29-31 falls through.
 *
 * Both exports behave identically in these five respects:
 *
 * - They always resolve and never reject. A suite that needs a consumer's
 *   `catch` branch installs the rejection itself, with `jest.mock()` plus
 *   `mockRejectedValue`.
 * - They perform no network, timer or filesystem work and read no clock or
 *   random source, so each call yields the same values on every run.
 * - They read none of their arguments and forward none of them, so a spy records
 *   the caller's own object exactly as the caller passed it.
 * - They allocate a fresh result object, including fresh nested arrays, on every
 *   call, so a caller that mutates one result cannot affect a later one.
 * - They write nothing to the console at all, leaving each consumer's own error
 *   message as the only one a suite observes.
 */

/**
 * Structural equivalent of the `DateRange` interface declared at lines 5-8 of
 * `frontend/src/components/Analytics`. That declaration is local to the
 * component module and carries no `export`, so it is not importable.
 */
export interface DateRange {
  startDate: string;
  endDate: string;
}

/**
 * Shape returned by {@link getTrendData}. `labels` and `values` are the only two
 * members any consumer reads: `frontend/src/components/Analytics` passes them to
 * Chart.js as the line dataset's labels (line 43) and data (line 47).
 */
export interface TrendSeries {
  labels: string[];
  values: number[];
}

/** One AI coding tool's mention volume within an {@link AnalyticsSummary}. */
export interface AiToolComparisonEntry {
  tool: string;
  mentions: number;
  averageDoubtRating: number;
}

/** Aggregate engagement totals within an {@link AnalyticsSummary}. */
export interface UserEngagementSummary {
  totalLikes: number;
  totalRetweets: number;
  totalReplies: number;
}

/**
 * Shape returned by {@link getAnalyticsData}. The three members correspond to
 * the three reads at lines 39-41 of `frontend/src/pages/Analytics.tsx`, which
 * forwards `trends` to `TrendCharts` at line 39. `trends` carries the same
 * {@link TrendSeries} shape that {@link getTrendData} resolves with.
 */
export interface AnalyticsSummary {
  trends: TrendSeries;
  aiToolComparison: AiToolComparisonEntry[];
  userEngagement: UserEngagementSummary;
}

/**
 * Resolves with a fixed trend series.
 *
 * Called by `frontend/src/components/Analytics` at line 16 with the component's
 * whole `dateRange` prop as its only argument. `dateRange` is accepted to fix
 * the arity and is neither read nor forwarded.
 *
 * @param dateRange - The caller's `{ startDate, endDate }` object.
 * @returns A promise resolving with a freshly allocated {@link TrendSeries}.
 *
 * @example
 * const trend = await getTrendData({ startDate: '2024-01-01', endDate: '2024-01-31' });
 * // trend.labels -> ['2024-01-01', '2024-01-02', '2024-01-03']
 * // trend.values -> [4, 9, 6]
 */
export const getTrendData = async (dateRange: DateRange): Promise<TrendSeries> => ({
  labels: ['2024-01-01', '2024-01-02', '2024-01-03'],
  values: [4, 9, 6],
});

/**
 * Resolves with a fixed, non-falsy analytics summary.
 *
 * Called by `frontend/src/pages/Analytics.tsx` at line 18 with three arguments.
 * All three are accepted to fix the arity and none is read or forwarded.
 *
 * @param start - Start of the caller's reporting window.
 * @param end - End of the caller's reporting window.
 * @param userId - Identifier of the user the caller is reporting on.
 * @returns A promise resolving with a freshly allocated {@link AnalyticsSummary}.
 *
 * @example
 * const summary = await getAnalyticsData(new Date(0), new Date(0), 'u1');
 * // summary.trends.values -> [4, 9, 6]
 * // summary.aiToolComparison.length -> 2
 * // summary.userEngagement.totalLikes -> 120
 */
export const getAnalyticsData = async (
  start: Date,
  end: Date,
  userId: string
): Promise<AnalyticsSummary> => ({
  trends: {
    labels: ['2024-01-01', '2024-01-02', '2024-01-03'],
    values: [4, 9, 6],
  },
  aiToolComparison: [
    { tool: 'GitHub Copilot', mentions: 9, averageDoubtRating: 0.8 },
    { tool: 'ChatGPT', mentions: 6, averageDoubtRating: 0.6 },
  ],
  userEngagement: {
    totalLikes: 120,
    totalRetweets: 45,
    totalReplies: 18,
  },
});

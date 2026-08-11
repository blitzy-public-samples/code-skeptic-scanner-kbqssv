/**
 * Test-side implementation of the module specifier `@/services/analyticsService`,
 * which has no implementation under `frontend/src/services`.
 *
 * `getTrendData` is called by `frontend/src/components/Analytics` with one
 * argument, the whole `{ startDate, endDate }` range; `getAnalyticsData` by
 * `frontend/src/pages/Analytics.tsx` with three. Both always resolve, read none
 * of their arguments, allocate a fresh result - including fresh nested arrays -
 * on every call, and write nothing to the console.
 */

/**
 * Structural equivalent of the `DateRange` interface `frontend/src/components/Analytics`
 * declares locally without an `export`, so it cannot be imported from there.
 */
export interface DateRange {
  startDate: string;
  endDate: string;
}

/** `frontend/src/components/Analytics` passes these to Chart.js as labels and data. */
export interface TrendSeries {
  labels: string[];
  values: number[];
}

export interface AiToolComparisonEntry {
  tool: string;
  mentions: number;
  averageDoubtRating: number;
}

export interface UserEngagementSummary {
  totalLikes: number;
  totalRetweets: number;
  totalReplies: number;
}

/**
 * The three members `frontend/src/pages/Analytics.tsx` reads; it forwards
 * `trends` to `TrendCharts`, which is why that member repeats the
 * {@link TrendSeries} shape {@link getTrendData} resolves with.
 */
export interface AnalyticsSummary {
  trends: TrendSeries;
  aiToolComparison: AiToolComparisonEntry[];
  userEngagement: UserEngagementSummary;
}

/** Resolves with a fixed {@link TrendSeries}. */
export const getTrendData = async (dateRange: DateRange): Promise<TrendSeries> => ({
  labels: ['2024-01-01', '2024-01-02', '2024-01-03'],
  values: [4, 9, 6],
});

/**
 * Resolves with a fixed, non-falsy {@link AnalyticsSummary}, so a consumer's
 * `if (!analyticsData)` guard falls through.
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

/**
 * Harness stand-in for the module specifier `../schema/configSchema`.
 *
 * `frontend/src/store/configSlice.ts` imports `Config` from
 * `../schema/configSchema` at line 2, and `frontend/src/schema/` ships only
 * `tweetSchema.ts` and `userSchema.ts`. The resolver in
 * `e2e/vite.harness.config.ts` redirects that specifier here while that remains
 * true.
 */

/**
 * Configuration record held as `state.config` by
 * `frontend/src/store/configSlice.ts`: declared at line 5, seeded as
 * `{} as Config` at line 11, and merged as `Partial<Config>` at line 20.
 *
 * The three sections are those `frontend/src/pages/Configuration.tsx` reads at
 * lines 53, 57 and 61. Every member, at every depth, is optional.
 */
export interface Config {
  /**
   * Credential section. The four members are the payload
   * `frontend/src/components/Configuration` assembles at lines 14-19.
   */
  twitterAPI?: {
    apiKey?: string;
    apiSecret?: string;
    accessToken?: string;
    accessTokenSecret?: string;
  };

  /** Language-model section. */
  llm?: {
    model?: string;
    temperature?: number;
    maxTokens?: number;
  };

  /**
   * Threshold section. The two members mirror `POPULARITY_THRESHOLD` and
   * `DOUBT_RATING_THRESHOLD` in `backend/app/core/config.py`.
   */
  thresholds?: {
    popularity?: number;
    doubtRating?: number;
  };
}

/** A `Config` with no section set. */
export const defaultConfig: Config = {};

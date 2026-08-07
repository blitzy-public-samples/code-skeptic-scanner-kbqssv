/**
 * Harness stand-in for the module specifier `../schema/configSchema`.
 *
 * `frontend/src/store/configSlice.ts` line 2 imports `Config` from
 * `../schema/configSchema`, and `frontend/src/schema/` ships only
 * `tweetSchema.ts` and `userSchema.ts`. The resolver in
 * `e2e/vite.harness.config.ts` redirects the specifier here while that remains
 * true.
 *
 * The import is type-only, so esbuild erases it and this module is normally never
 * requested at runtime. It exists so the module graph stays resolvable.
 */

/**
 * Twitter API credential section. The four members mirror the payload that
 * `frontend/src/components/Configuration` passes to `updateTwitterAPIConfig`
 * (lines 14-19). Every member is optional.
 */
export interface TwitterAPIConfig {
  /** Twitter API consumer key. */
  apiKey?: string;
  /** Twitter API consumer secret. */
  apiSecret?: string;
  /** Twitter API access token. */
  accessToken?: string;
  /** Twitter API access token secret. */
  accessTokenSecret?: string;
}

/**
 * Language-model section. The members mirror the completion parameters that
 * `backend/app/services/llm_service.py` passes to `Completion.create`. Every
 * member is optional.
 */
export interface LLMConfig {
  /** Completion engine identifier; mirrors the backend's `openai_engine`. */
  engine?: string;
  /** Token ceiling; mirrors the backend's `max_tokens` completion parameter. */
  maxTokens?: number;
  /** Sampling temperature; mirrors the backend's `temperature` parameter. */
  temperature?: number;
}

/**
 * Ingestion threshold section. The members mirror the two threshold constants
 * declared in `backend/app/core/config.py`. Every member is optional.
 */
export interface ThresholdsConfig {
  /** Engagement threshold; mirrors the backend's `POPULARITY_THRESHOLD`. */
  popularity?: number;
  /** Doubt-rating threshold; mirrors the backend's `DOUBT_RATING_THRESHOLD`. */
  doubtRating?: number;
}

/**
 * Configuration record held as `state.config` by
 * `frontend/src/store/configSlice.ts`.
 *
 * Every section is optional because the slice's initial state is `{} as Config`
 * (line 11) and `updateConfig` accepts a `Partial<Config>` (line 20).
 */
export interface Config {
  twitterAPI?: TwitterAPIConfig;
  llm?: LLMConfig;
  thresholds?: ThresholdsConfig;
}

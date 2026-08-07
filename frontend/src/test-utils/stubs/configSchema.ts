/**
 * Test-only stand-in for the module specifier `../schema/configSchema`, which
 * `frontend/src/store/configSlice.ts` imports `Config` from and which has no
 * implementation in this repository. Nothing imports this file directly.
 *
 * `Config` carries the three sections `frontend/src/pages/Configuration.tsx`
 * reads. Every member of every section is optional, because `configSlice.ts`
 * seeds the document as `{} as Config` and merges `Partial<Config>` into it.
 */

export interface TwitterAPIConfig {
  apiKey?: string;
  apiSecret?: string;
  accessToken?: string;
  accessTokenSecret?: string;
}

export interface LLMConfig {
  /** Completion engine identifier; mirrors the backend's `openai_engine`. */
  engine?: string;
  /** Token ceiling; mirrors the backend's `max_tokens` completion parameter. */
  maxTokens?: number;
  /** Sampling temperature; mirrors the backend's `temperature` parameter. */
  temperature?: number;
}

export interface ThresholdsConfig {
  /** Engagement threshold; mirrors the backend's `POPULARITY_THRESHOLD`. */
  popularity?: number;
  /** Doubt-rating threshold; mirrors the backend's `DOUBT_RATING_THRESHOLD`. */
  doubtRating?: number;
}

export interface Config {
  twitterAPI?: TwitterAPIConfig;
  llm?: LLMConfig;
  thresholds?: ThresholdsConfig;
}

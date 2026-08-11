/**
 * Test-only stand-in for the module specifier `../schema/configSchema`, which
 * `frontend/src/store/configSlice.ts` imports `Config` from and which has no
 * implementation in this repository.
 *
 * Two routes reach it, and they are not interchangeable. Production modules keep
 * their own specifier and are redirected here by `frontend/jest.config.js`, whose
 * `moduleNameMapper` carries both forms the sources use, `^\.\./schema/configSchema$`
 * and `^@/schema/configSchema$`. Test modules may import this path directly, and
 * `frontend/src/pages/Configuration.test.tsx` does, for the `Config` type it annotates
 * its fixtures with - a type-only import, erased by the transform, so it adds no
 * runtime edge to the graph.
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

/**
 * Test-only stand-in for the module specifier `../schema/configSchema`.
 *
 * `frontend/src/store/configSlice.ts` line 2 imports `Config` from
 * `../schema/configSchema`. No such module exists in this repository, so the
 * Jest `moduleNameMapper` in `frontend/jest.config.js` redirects that specifier
 * to this file. Nothing imports this file directly.
 *
 * Every `moduleNameMapper` group, and the source import each one serves, is
 * documented in `frontend/TESTING.md`.
 */

/**
 * Twitter API credential section, read as `config.twitterAPI` by
 * `frontend/src/pages/Configuration.tsx` line 53.
 *
 * The four members mirror the payload that
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
 * Language-model section, read as `config.llm` by
 * `frontend/src/pages/Configuration.tsx` line 57.
 *
 * The members mirror the completion parameters that
 * `backend/app/services/llm_service.py` passes to `Completion.create`.
 * Every member is optional.
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
 * Ingestion threshold section, read as `config.thresholds` by
 * `frontend/src/pages/Configuration.tsx` line 61.
 *
 * The members mirror the two threshold constants declared in
 * `backend/app/core/config.py`. Every member is optional.
 */
export interface ThresholdsConfig {
  /** Engagement threshold; mirrors the backend's `POPULARITY_THRESHOLD`. */
  popularity?: number;
  /** Doubt-rating threshold; mirrors the backend's `DOUBT_RATING_THRESHOLD`. */
  doubtRating?: number;
}

/**
 * Configuration document consumed by `frontend/src/store/configSlice.ts`.
 *
 * The three sections are the members that
 * `frontend/src/pages/Configuration.tsx` reads off a configuration value
 * (lines 53, 57 and 61). Every member is optional. `configSlice.ts` seeds this
 * document as `{} as Config` (line 11) and merges `Partial<Config>` payloads
 * into it (line 20).
 */
export interface Config {
  /** Twitter API credentials. */
  twitterAPI?: TwitterAPIConfig;
  /** Language-model completion settings. */
  llm?: LLMConfig;
  /** Ingestion thresholds. */
  thresholds?: ThresholdsConfig;
}

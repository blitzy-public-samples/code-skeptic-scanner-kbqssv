/**
 * Harness stand-in for the module specifier `../schema/configSchema`.
 *
 * `frontend/src/store/configSlice.ts` imports `Config` from
 * `../schema/configSchema` at line 2, and `frontend/src/schema/` ships only
 * `tweetSchema.ts` and `userSchema.ts`. The resolver in
 * `e2e/vite.harness.config.ts` redirects that specifier here while that remains
 * true.
 *
 * `Config` is the only export, and it is a type. The module holds no value and
 * therefore no state that could carry from one spec into the next. Its member
 * names match `frontend/src/test-utils/stubs/configSchema.ts`, the Jest-side
 * stand-in for the same missing module.
 */

/**
 * Configuration record held as `state.config` by
 * `frontend/src/store/configSlice.ts`, which seeds it as `{} as Config` and merges
 * `Partial<Config>` into it. Every member, at every depth, is optional.
 */
export interface Config {
  twitterAPI?: {
    apiKey?: string;
    apiSecret?: string;
    accessToken?: string;
    accessTokenSecret?: string;
  };

  /**
   * Language-model section. `engine` mirrors the `openai_engine` that
   * `backend/app/services/llm_service.py` reads, and `maxTokens` and
   * `temperature` mirror the `max_tokens` and `temperature` completion
   * parameters it passes. The member names match
   * `frontend/src/test-utils/stubs/configSchema.ts`, so the Jest-side and
   * harness-side stand-ins for this one missing module describe the same shape.
   */
  llm?: {
    engine?: string;
    maxTokens?: number;
    temperature?: number;
  };

  thresholds?: {
    popularity?: number;
    doubtRating?: number;
  };
}

/**
 * Harness stand-in for the module specifier `@/services/configService`.
 *
 * `frontend/src/services/` ships only `api.ts`, `llmService.ts` and
 * `twitterService.ts`, so the specifier that
 * `frontend/src/components/Configuration` imports at line 3 has no implementation
 * in the repository. The resolver in `e2e/vite.harness.config.ts` redirects it
 * here while that remains true.
 *
 * Always resolves, so the component takes its success branch and raises the
 * `alert` at line 20. Performs no network work.
 */

/**
 * Credential payload the component assembles at lines 14-19 of
 * `frontend/src/components/Configuration` from its four controlled inputs.
 */
export interface TwitterAPIConfigPayload {
  apiKey: string;
  apiSecret: string;
  accessToken: string;
  accessTokenSecret: string;
}

/** Result of a successful {@link updateTwitterAPIConfig} call. */
export interface ConfigUpdateResult {
  updated: boolean;
}

/**
 * Called as `updateTwitterAPIConfig({ apiKey, apiSecret, accessToken,
 * accessTokenSecret })` at line 14 of `frontend/src/components/Configuration`.
 *
 * The argument is deliberately unread so that a spy records the caller's own
 * object exactly as the caller passed it.
 */
export async function updateTwitterAPIConfig(
  config: TwitterAPIConfigPayload,
): Promise<ConfigUpdateResult> {
  void config;
  return { updated: true };
}

/**
 * Test-side implementation of the module specifier `@/services/configService`.
 *
 * `frontend/src/services/` ships only `api.ts`, `llmService.ts` and
 * `twitterService.ts`, so `@/services/configService` has no implementation in
 * the repository. Under Jest the specifier resolves to this file through the
 * `moduleNameMapper` entry in `frontend/jest.config.js`, which is listed with
 * every other mapper group in `frontend/TESTING.md`.
 *
 * The three consuming call sites fix the three signatures below.
 *
 * `frontend/src/components/Configuration` imports `updateTwitterAPIConfig` at
 * line 3 and calls it at lines 14-19 with one object literal carrying the four
 * `useState('')` values declared at lines 6-9 and bound to the labelled inputs
 * at lines 31, 41, 51 and 61. The component discards the resolved value and
 * reaches `alert('Twitter API settings updated successfully')` at line 20.
 *
 * `frontend/src/pages/Configuration.tsx` imports `getConfig` and `updateConfig`
 * at line 3. It calls `getConfig()` with no arguments at line 20 and forwards
 * the resolved document into the config slice at line 21, then calls
 * `updateConfig(updatedConfig)` with one argument at line 34. The `updateConfig`
 * exported here is the service function; that page separately imports the
 * config-slice action creator of the same name, aliased to `updateConfigAction`
 * at line 5.
 *
 * All three exports behave identically in these five respects:
 *
 * - They always resolve and never reject. A suite that needs a consumer's
 *   `catch` branch installs the rejection itself, with `jest.mock()` plus
 *   `mockRejectedValue`.
 * - They perform no network, timer or filesystem work and read no clock or
 *   random source, so each call yields the same values on every run.
 * - They never mutate an argument, so a spy installed over any of them records
 *   the caller's own object exactly as the caller built it.
 * - They allocate a fresh result on every call, so a caller that mutates one
 *   result cannot affect a later one.
 * - They write nothing to the console at all, leaving each consumer's own error
 *   message as the only one a suite observes.
 *
 * Recorded design decisions: `docs/testing/DECISION-LOG.md`.
 */

import type { Config } from './configSchema';

/**
 * Credential payload accepted by {@link updateTwitterAPIConfig}.
 *
 * The four members are the `useState('')` values declared at lines 6-9 of
 * `frontend/src/components/Configuration` and assembled into a single object
 * literal at lines 14-19, in this order. All four are required strings.
 *
 * Distinct from the `TwitterAPIConfig` of `./configSchema`, which is the
 * corresponding section of a stored configuration document and declares every
 * member optional. The two shapes are not interchangeable.
 */
export interface TwitterAPICredentials {
  /** Twitter API consumer key; the `API Key:` input at line 31. */
  apiKey: string;
  /** Twitter API consumer secret; the `API Secret:` input at line 41. */
  apiSecret: string;
  /** Twitter API access token; the `Access Token:` input at line 51. */
  accessToken: string;
  /**
   * Twitter API access token secret; the `Access Token Secret:` input at line
   * 61.
   */
  accessTokenSecret: string;
}

/**
 * Acknowledgement resolved by {@link updateTwitterAPIConfig}.
 *
 * `frontend/src/components/Configuration` discards the resolved value at line
 * 14. Both members below are fixed literals and carry no data from the call.
 */
export interface ConfigUpdateAcknowledgement {
  /** Always `true`; the acknowledgement is only ever resolved, never rejected. */
  updated: boolean;
  /** Name of the {@link Config} section the call addressed. */
  section: string;
}

/**
 * Resolves with a fixed acknowledgement that the Twitter credential section was
 * written.
 *
 * Called by `frontend/src/components/Configuration` at lines 14-19 with one
 * object carrying the four credential fields. `credentials` is accepted to fix
 * the arity and is neither read, copied nor forwarded, so a spy installed over
 * this export records the caller's object unchanged.
 *
 * @param credentials - The caller's
 * `{ apiKey, apiSecret, accessToken, accessTokenSecret }` object.
 * @returns A promise resolving with a freshly allocated
 * {@link ConfigUpdateAcknowledgement}.
 *
 * @example
 * await updateTwitterAPIConfig({
 *   apiKey: 'k',
 *   apiSecret: 's',
 *   accessToken: 't',
 *   accessTokenSecret: 'ts',
 * });
 * // -> { updated: true, section: 'twitterAPI' }
 */
export const updateTwitterAPIConfig = async (
  credentials: TwitterAPICredentials
): Promise<ConfigUpdateAcknowledgement> => ({
  updated: true,
  section: 'twitterAPI',
});

/**
 * Resolves with a fully populated configuration document.
 *
 * Called by `frontend/src/pages/Configuration.tsx` at line 20 with no
 * arguments; the resolved document is dispatched into the config slice at line
 * 21 as a `Partial<Config>` payload. All three sections are present, so the
 * page's reads of `config.twitterAPI`, `config.llm` and `config.thresholds` at
 * lines 53, 57 and 61 are defined.
 *
 * The `llm` members carry the `max_tokens` and `temperature` arguments that
 * `backend/app/services/llm_service.py` passes to `Completion.create`, and the
 * `thresholds` members carry `POPULARITY_THRESHOLD` and
 * `DOUBT_RATING_THRESHOLD` from lines 20-21 of `backend/app/core/config.py`.
 * The four credential strings are placeholders and authenticate against
 * nothing.
 *
 * @returns A promise resolving with a freshly allocated {@link Config} whose
 * three sections are themselves fresh objects.
 *
 * @example
 * const config = await getConfig();
 * // config.thresholds -> { popularity: 100, doubtRating: 0.7 }
 * // config.llm -> { engine: 'text-davinci-003', maxTokens: 150, temperature: 0.7 }
 */
export const getConfig = async (): Promise<Config> => ({
  twitterAPI: {
    apiKey: 'test-twitter-api-key',
    apiSecret: 'test-twitter-api-secret',
    accessToken: 'test-twitter-access-token',
    accessTokenSecret: 'test-twitter-access-token-secret',
  },
  llm: {
    engine: 'text-davinci-003',
    maxTokens: 150,
    temperature: 0.7,
  },
  thresholds: {
    popularity: 100,
    doubtRating: 0.7,
  },
});

/**
 * Resolves with the configuration document it was handed.
 *
 * Called by `frontend/src/pages/Configuration.tsx` at line 34 with the single
 * object its `handleSave` receives, typed `any` at that call site. The argument
 * is spread into a new object, so the resolved value equals the argument
 * without being the same instance and the caller's object is left untouched.
 * Nested sections are shared with the argument, as a shallow copy implies.
 *
 * This is the service function of that name. The config-slice action creator
 * `updateConfig`, exported by `frontend/src/store/configSlice.ts` at line 32,
 * is a different symbol and is not referenced here.
 *
 * @param updatedConfig - Sections the caller is saving.
 * @returns A promise resolving with a shallow copy of `updatedConfig`.
 *
 * @example
 * const saved = await updateConfig({ thresholds: { popularity: 250 } });
 * // saved.thresholds -> { popularity: 250 }
 */
export const updateConfig = async (
  updatedConfig: Partial<Config>
): Promise<Partial<Config>> => ({ ...updatedConfig });

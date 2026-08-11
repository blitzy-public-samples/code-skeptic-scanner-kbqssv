/**
 * Test-side implementation of the module specifier `@/services/configService`, which has no implementation
 * under `frontend/src/services`. All three exports always resolve, persist nothing, never mutate an
 * argument, allocate a fresh result on every call, and write nothing to the console.
 *
 * The `updateConfig` here is the service function; `frontend/src/pages/Configuration.tsx` separately imports
 * the config-slice action creator of the same name, under an alias.
 */

import type { Config } from './configSchema';

/**
 * The four values `frontend/src/components/Configuration` binds to its labelled inputs, all required.
 * Distinct from `./configSchema`'s `TwitterAPIConfig`, the section of a stored document whose members are all
 * optional; the two shapes are not interchangeable.
 */
export interface TwitterAPICredentials {
  apiKey: string;
  apiSecret: string;
  accessToken: string;
  accessTokenSecret: string;
}

export interface ConfigUpdateAcknowledgement {
  updated: boolean;
  section: string;
}

/** Resolves with `{ updated: true, section: 'twitterAPI' }`. */
export const updateTwitterAPIConfig = async (
  credentials: TwitterAPICredentials
): Promise<ConfigUpdateAcknowledgement> => ({
  updated: true,
  section: 'twitterAPI',
});

/**
 * Resolves with a fully populated {@link Config}, so a consumer's reads of `config.twitterAPI`, `config.llm`
 * and `config.thresholds` are all defined. The `llm` and `thresholds` values mirror the backend's completion
 * parameters and threshold constants; the credential strings are placeholders that authenticate nothing.
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
 * Resolves with a shallow copy of the document it was handed: equal to the argument without being the same
 * instance, and sharing its nested sections.
 */
export const updateConfig = async (
  updatedConfig: Partial<Config>
): Promise<Partial<Config>> => ({ ...updatedConfig });

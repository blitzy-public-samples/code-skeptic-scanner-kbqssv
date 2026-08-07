/**
 * Harness stand-in for the module specifier `@/services/configService`.
 *
 * `frontend/src/components/Configuration` imports `updateTwitterAPIConfig` from
 * this specifier at line 3. `frontend/src/services/` ships only `api.ts`,
 * `llmService.ts` and `twitterService.ts`, and the resolver in
 * `e2e/vite.harness.config.ts` redirects the specifier here while no module
 * exists at `frontend/src/services/configService`.
 */

/**
 * Credential payload `frontend/src/components/Configuration` assembles at lines
 * 14-19 from its four controlled inputs. Every member is required, matching the
 * four `required` inputs the form declares.
 */
interface TwitterAPICredentials {
  apiKey: string;
  apiSecret: string;
  accessToken: string;
  accessTokenSecret: string;
}

/** Path the credential payload is posted to, relative to the serving origin. */
const CONFIG_ENDPOINT = '/api/config/twitter';

/**
 * Posts the credential payload to `/api/config/twitter` as JSON.
 *
 * Rejects with an `Error` naming the endpoint and the HTTP status whenever the
 * response status falls outside the 2xx range. Otherwise resolves with the parsed
 * response body, or with `undefined` when the response carries no body.
 *
 * Called as `updateTwitterAPIConfig({ apiKey, apiSecret, accessToken,
 * accessTokenSecret })` at line 14 of `frontend/src/components/Configuration`,
 * which reads only whether the returned promise settles or rejects.
 */
export const updateTwitterAPIConfig = async (
  credentials: TwitterAPICredentials
): Promise<unknown> => {
  const response = await fetch(CONFIG_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(credentials),
  });

  // Status check, placed ahead of every read of the body.
  if (!response.ok) {
    throw new Error(
      `POST ${CONFIG_ENDPOINT} failed with HTTP status ${response.status}`
    );
  }

  // The body is consumed once, as text, and parsed only when non-empty.
  const body = await response.text();
  return body === '' ? undefined : JSON.parse(body);
};

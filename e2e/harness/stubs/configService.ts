/**
 * Harness stand-in for the specifier `@/services/configService`, which
 * `frontend/src/components/Configuration` imports and `frontend/src/services/` does
 * not provide. `e2e/vite.harness.config.ts` redirects that specifier here.
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
 * @param credentials - The four values the caller's form collects, sent verbatim
 *   as the request body.
 * @returns The parsed response body, or `undefined` when the response carries no
 *   body.
 * @throws Error - When the response status falls outside 200-299. The message
 *   names the endpoint and that status.
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

  if (!response.ok) {
    throw new Error(
      `POST ${CONFIG_ENDPOINT} failed with HTTP status ${response.status}`
    );
  }

  const body = await response.text();
  return body === '' ? undefined : JSON.parse(body);
};

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
 * The body is read to completion on both the ok and the non-ok path, so the response
 * is never left with an open stream.
 *
 * @param credentials - The four values the caller's form collects, sent verbatim
 *   as the request body.
 * @returns The parsed response body, or `undefined` when the response carries no
 *   body.
 * @throws Error - When the response status falls outside 200-299. The body is read to
 *   completion and discarded first, so the message names the endpoint and that status
 *   and carries neither the response body nor any submitted credential.
 * @see docs/testing/DECISION-LOG.md - row D143, the non-ok body read.
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
    // Drains the body and discards it; a read failure here changes nothing that follows.
    await response.text().catch(() => undefined);
    throw new Error(
      `POST ${CONFIG_ENDPOINT} failed with HTTP status ${response.status}`
    );
  }

  const body = await response.text();
  return body === '' ? undefined : JSON.parse(body);
};

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
 * Longest response-body excerpt a status error carries.
 *
 * Bounded so that an error page or a large payload answered by mistake cannot turn one console
 * line into a wall of text. Every reason this harness's own responders produce - the
 * `503 harness-api-not-intercepted` document, and the small JSON objects a spec fulfils a
 * failing route with - fits inside it whole.
 */
const BODY_EXCERPT_LIMIT = 300;

/** Excerpt used when the response carried no body at all. */
const EMPTY_BODY_EXCERPT = '(no body)';

/** Excerpt used when reading the body itself failed, which the caller never sees as a rejection. */
const UNREADABLE_BODY_EXCERPT = '(body could not be read)';

/** What a submitted credential is replaced by if a response echoes one back. */
const REDACTED_CREDENTIAL = '[redacted credential]';

/**
 * Reduces a response body to one bounded, single-line excerpt fit for an error message, with
 * every submitted credential removed from it first.
 *
 * The order matters and is the whole point. Redaction runs over the **full** body before it is
 * truncated, so no credential can survive as the tail of a cut-off excerpt; and it runs over every
 * non-empty value the caller submitted, so a responder that echoes the payload back - an
 * unremarkable thing for a validating endpoint to do - cannot put a credential on a console line,
 * into a Playwright trace, or into a screenshot of the devtools panel. Without this, surfacing the
 * body at all would trade a diagnostic gain for a credential leak.
 *
 * Only whole occurrences are replaced. A responder that echoes a *fragment* of a value would still
 * place that fragment in the excerpt; the values a spec types are synthetic, and the harness's own
 * responders echo the request line rather than the body, so nothing here relies on that case.
 *
 * @param body - Response body, read to completion.
 * @param submitted - The credential values this request carried, in any order.
 * @returns The redacted, single-line, bounded excerpt, or {@link EMPTY_BODY_EXCERPT}.
 */
function excerptResponseBody(body: string, submitted: readonly string[]): string {
  let redacted = body;
  for (const credential of submitted) {
    if (credential !== '') {
      redacted = redacted.split(credential).join(REDACTED_CREDENTIAL);
    }
  }

  const collapsed = redacted.replace(/\s+/g, ' ').trim();

  if (collapsed === '') {
    return EMPTY_BODY_EXCERPT;
  }

  if (collapsed.length <= BODY_EXCERPT_LIMIT) {
    return collapsed;
  }

  return `${collapsed.slice(0, BODY_EXCERPT_LIMIT)}... (${collapsed.length} characters in total)`;
}

/**
 * Posts the credential payload to `/api/config/twitter` as JSON.
 *
 * The body is read to completion on both the ok and the non-ok path.
 *
 * @param credentials - The four values the caller's form collects, sent verbatim
 *   as the request body.
 * @returns The parsed response body, or `undefined` when the response carries no
 *   body.
 * @throws Error - When the response status falls outside 200-299. The body is read to
 *   completion first, and the message names the endpoint, that status and a bounded excerpt
 *   of that body - so a reason the responder supplied, such as `config-write-refused` or this
 *   harness's own `harness-api-not-intercepted` remedy, reaches the caller's console instead of
 *   being discarded. **No submitted credential can appear in that excerpt**: every value this
 *   request carried is removed from the body before it is truncated. See
 *   {@link excerptResponseBody}.
 * @see docs/testing/DECISION-LOG.md - row D143, the non-ok body read, and row D394, which
 *   carries what that read produced into the thrown message under redaction.
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
    /*
     * Drains the body (D143), then carries a redacted, bounded excerpt of it into the message
     * (D394). The read is still what makes the request visible to the resource timeline and its
     * body retrievable from the debugger; what changed is that the reason it holds is no longer
     * thrown away. A read failure yields a fixed excerpt rather than a rejection of its own, so
     * the status error below is thrown on every path either way.
     */
    const excerpt = await response
      .text()
      .then((body) => excerptResponseBody(body, Object.values(credentials)))
      .catch(() => UNREADABLE_BODY_EXCERPT);

    throw new Error(
      `POST ${CONFIG_ENDPOINT} failed with HTTP status ${response.status}. ` +
        `Response body: ${excerpt}`
    );
  }

  const body = await response.text();
  return body === '' ? undefined : JSON.parse(body);
};

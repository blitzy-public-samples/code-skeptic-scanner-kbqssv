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
 * Most the redaction may grow a body before its text is withheld instead of excerpted.
 *
 * The replacement token is longer than a short credential, so redacting one lengthens the body
 * rather than shortening it. A realistic echo - four values of a dozen characters or more, each
 * appearing once - moves the length by a few per cent. A degenerate one - a value one or two
 * characters long, which matches all over the body - can multiply it, and what comes back is a
 * wall of placeholders in which none of the responder's own words survives. Past this factor the
 * excerpt has stopped carrying a diagnostic, so {@link withheldBodyExcerpt} states the body's
 * shape instead of showing text that says nothing.
 */
const MAX_REDACTED_GROWTH_FACTOR = 2;

/**
 * Excerpt used when redaction left no readable text, stating the shape rather than the content.
 *
 * @param bodyLength - Length of the response body as it was read.
 * @param occurrences - How many submitted values were replaced in it.
 * @returns A fixed-shape sentence carrying no body text at all.
 */
function withheldBodyExcerpt(bodyLength: number, occurrences: number): string {
  return (
    `(body withheld: ${occurrences} occurrence(s) of the submitted values in its ` +
    `${bodyLength} characters left no readable excerpt after redaction)`
  );
}

/**
 * Replaces every submitted credential in `body` in one left-to-right pass.
 *
 * One pass is the correctness property, not an optimisation. Replacing the values one at a time -
 * a `split`/`join` per value over the output of the last - re-examines text that already holds
 * {@link REDACTED_CREDENTIAL}, and that token contains the characters a short credential is made
 * of, so such a credential re-redacts its own replacement once per remaining value. A single scan
 * copies each replacement to the output and never reads it again, which bounds the result at the
 * body's length times the token's however short the values are.
 *
 * Longest first, and de-duplicated, for the other half of the same property: one submitted value
 * can be a prefix of another - `test-access-token` of `test-access-token-secret` - and replacing
 * the shorter one first consumes the prefix and leaves the remainder (`-secret`) in the excerpt as
 * a fragment of a credential. Matching the longest candidate at each position removes that case.
 *
 * @param body - Response body, read to completion.
 * @param submitted - The credential values this request carried, in any order.
 * @returns The redacted text and how many replacements it took.
 */
function redactSubmittedValues(
  body: string,
  submitted: readonly string[]
): { redacted: string; occurrences: number } {
  const needles = Array.from(new Set(submitted.filter((value) => value !== ''))).sort(
    (left, right) => right.length - left.length
  );

  if (needles.length === 0) {
    return { redacted: body, occurrences: 0 };
  }

  let redacted = '';
  let occurrences = 0;
  let index = 0;

  while (index < body.length) {
    const matched = needles.find((needle) => body.startsWith(needle, index));

    if (matched === undefined) {
      redacted += body[index];
      index += 1;
      continue;
    }

    redacted += REDACTED_CREDENTIAL;
    occurrences += 1;
    index += matched.length;
  }

  return { redacted, occurrences };
}

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
 * Redaction is a single pass over the body - see {@link redactSubmittedValues} - so the text it
 * produces is bounded by the body it read, and every whole occurrence of every submitted value is
 * replaced whether or not one value contains another. A responder that echoes a *fragment* of a
 * value would still place that fragment in the excerpt; the values a spec types are synthetic, and
 * the harness's own responders echo the request line rather than the body, so nothing here relies
 * on that case.
 *
 * When the replacements dominate what is left - {@link MAX_REDACTED_GROWTH_FACTOR} - the body's
 * text is withheld entirely rather than excerpted, because a line of nothing but placeholders is
 * not a diagnostic. {@link withheldBodyExcerpt} states its size and how many values were found in
 * it, which is what a reader can act on, and carries no body text.
 *
 * @param body - Response body, read to completion.
 * @param submitted - The credential values this request carried, in any order.
 * @returns The redacted, single-line, bounded excerpt, {@link EMPTY_BODY_EXCERPT}, or the
 *   withheld-body statement.
 */
function excerptResponseBody(body: string, submitted: readonly string[]): string {
  const { redacted, occurrences } = redactSubmittedValues(body, submitted);

  if (redacted.length > body.length * MAX_REDACTED_GROWTH_FACTOR) {
    return withheldBodyExcerpt(body.length, occurrences);
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
 *   request carried is removed from the body before it is truncated, in one pass, and where that
 *   redaction would leave nothing readable the body's text is withheld altogether. See
 *   {@link excerptResponseBody}.
 * @see docs/testing/DECISION-LOG.md - row D143, the non-ok body read; row D394, which carries
 *   what that read produced into the thrown message under redaction; and row D409, which makes
 *   that redaction one pass and bounds what it can produce.
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

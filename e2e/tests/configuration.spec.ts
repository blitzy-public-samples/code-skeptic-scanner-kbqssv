/**
 * End-to-end coverage of the harness client route `/configuration`.
 *
 * Subject: `TwitterAPISettings`, the default export of `frontend/src/components/Configuration`,
 * which `e2e/harness/main.tsx` L76 mounts at `/configuration` with no props. That module is an
 * extension-less file; `e2e/vite.harness.config.ts` resolves and transforms it, and redirects the
 * `@/services/configService` specifier it imports at L3 to `e2e/harness/stubs/configService.ts`.
 *
 * `test` and `expect` come from `./harness-fixtures`, whose two automatic fixtures do the
 * cross-cutting work: `noEgress` aborts every request addressed off the harness origin and fails
 * the test at teardown for any harness API request no route below claimed - `/api/config/twitter`
 * being one of the three it names - and `browserDiagnostics` attaches the browser's console and
 * page errors and fails the test on any it did not declare. Each test therefore installs its own
 * interception before navigating, declares the failures it expects, and holds no state shared with
 * another test.
 *
 * Only the third test declares one. The first two assert a route that reports nothing to the
 * console, and the fixture is what holds them to it.
 *
 * This is the only route in the harness driven by user input rather than by a mount effect, so the
 * flow under test is: fill four fields, submit, and read the outcome the subject reports.
 *
 * What each test asserts, and the production lines it reads from:
 *
 * | Test | Behaviour asserted |
 * |------|--------------------|
 * | 1 | `components/Configuration` L28-L70 render one `<h2>`, four labelled required credential inputs of which two are `type="password"`, and one submit control |
 * | 2 | `components/Configuration` L14-L20 hand the four collected values to `updateTwitterAPIConfig` as a single four-key object, which `harness/stubs/configService.ts` L34-L40 posts as JSON, and then report success through `alert` |
 * | 3 | `components/Configuration` L21-L23 catch a rejection from that call, log it and report it through `alert`, leaving the route mounted rather than letting it propagate |
 * | 4 | Two of the four credential fields render their value in clear text, and none declares an autofill policy |
 * | 5 | The submit control expresses no pending state while the credential write is open, and a second activation issues a second write and a second dialog |
 *
 * The same component under Jest, with `updateTwitterAPIConfig` itself stubbed rather than its
 * transport intercepted, is covered by `frontend/src/components/Configuration.test.tsx`.
 *
 * ## Two ceilings this file pins rather than fixes
 *
 * Both would need an edit to `frontend/src/components/Configuration`, which is production code this
 * programme is not authorized to change, so each is characterised here as current behaviour.
 *
 * 1. **Two credential fields are unmasked.** L31-L38 render `API Key` and L51-L58 render
 *    `Access Token` as `type="text"`, so both values are visible on screen and in a screen share.
 *    Only the two `Secret`-suffixed fields are `type="password"`. No field declares `autocomplete`,
 *    so the browser's default handling applies to all four. Masking follows the field's *name*, not
 *    whether the value is a credential - and an API key and an access token authenticate exactly as
 *    their secrets do. Test 4 asserts this in a real browser, where the visible value is observable.
 * 2. **The submit has no pending state.** L11-L25 `handleSubmit` awaits the write but holds no state
 *    for it: the L70 button is never `disabled`, never carries `aria-busy`, and no status element is
 *    rendered. Test 5 activates the still-live control a second time mid-flight and records what
 *    follows - a second credential write to the same endpoint and a second dialog.
 * Every value this file types is an obvious test literal and no live secret is read anywhere in
 * this repository. Even so, the intercepted body reaches the report **redacted** to key names,
 * value presence, length and a short digest, while the assertions compare it in full: CI retains
 * these reports, and a format that carries whole credential-shaped bodies is one real fixture away
 * from carrying a real one.
 *
 * @see e2e/README.md - adding a spec to this directory.
 * @see docs/testing/DECISION-LOG.md - the dialog-handling, branch-selection and payload-assertion
 *   rows for this file, and row D260 for the attachment redaction.
 */

import { expect, HARNESS_ORIGIN, resourceFailure, test } from './harness-fixtures';

/* -------------------------------------------------------------------------- */
/* Oracles                                                                    */
/* -------------------------------------------------------------------------- */

/** Client route `e2e/harness/main.tsx` L76 mounts the subject at. Resolved against `use.baseURL`. */
const SETTINGS_ROUTE = '/configuration';

/** Element `components/Configuration` L28 renders as the subject's root. */
const SETTINGS_FORM = 'form';

/** Accessible name of the `<h2>` `components/Configuration` L29 renders. */
const SETTINGS_HEADING = 'Twitter API Settings';

/** Heading level of that element. */
const SETTINGS_HEADING_LEVEL = 2;

/** Accessible name of the submit control `components/Configuration` L70 renders. */
const SAVE_BUTTON = 'Save Twitter API Settings';

/** `type` of that control, which is what routes a click into the `onSubmit` handler at L28. */
const SAVE_BUTTON_TYPE = 'submit';

/**
 * Glob covering the credential request `harness/stubs/configService.ts` L34 issues. The same value
 * `e2e/vite.harness.config.ts` names as this endpoint's remedy in `HARNESS_API_SURFACE`.
 *
 * Anchored to {@link HARNESS_ORIGIN}, and it matters most here: this is the request that carries
 * credentials. A host-agnostic `'**\/api/config/twitter'` would claim - and this file's handlers
 * would fulfil - a POST addressed to a foreign host, so a test asserting the submitted body would
 * pass while the credentials had been sent somewhere else entirely. Anchored, such a request falls
 * through to the `noEgress` fixture, which aborts and records it. `./isolation.spec.ts` asserts
 * exactly that.
 */
const CONFIG_ENDPOINT_GLOB = `${HARNESS_ORIGIN}/api/config/twitter`;

/** Pathname of that request, after the browser resolves its relative URL against the harness origin. */
const CONFIG_ENDPOINT_PATHNAME = '/api/config/twitter';

/** Method it carries, from `harness/stubs/configService.ts` L35. */
const CONFIG_ENDPOINT_METHOD = 'POST';

/** Content type it declares, from `harness/stubs/configService.ts` L37. */
const CONFIG_ENDPOINT_CONTENT_TYPE = 'application/json';

/** Status inside the range `harness/stubs/configService.ts` L42 treats as ok. */
const OK_STATUS = 200;

/** Status outside that range, which drives `harness/stubs/configService.ts` L45 to throw. */
const REJECTED_STATUS = 500;

/** Message `components/Configuration` L20 alerts once the call resolves. */
const SUCCESS_ALERT = 'Twitter API settings updated successfully';

/** Message `components/Configuration` L23 alerts once the call rejects. */
const FAILURE_ALERT = 'Failed to update Twitter API settings';

/** Entry `components/Configuration` L22 writes on that path, in the form this file records it. */
const FAILURE_LOG = /console\.error: Error updating Twitter API settings:/;

/** Status the stub names in the error it throws, which L22 logs alongside its own prefix. */
const REJECTED_STATUS_IN_LOG = /HTTP status 500/;

/** Kind of dialog `alert` opens. */
const ALERT_DIALOG = 'alert';

/**
 * Request body `components/Configuration` L14-L19 build, keyed exactly as those lines name each
 * value and carrying no other key.
 *
 * Every value is an obvious test literal: no credential of any real service appears in this file.
 */
const EXPECTED_PAYLOAD = {
  apiKey: 'test-api-key',
  apiSecret: 'test-api-secret',
  accessToken: 'test-access-token',
  accessTokenSecret: 'test-access-token-secret',
} as const;

/**
 * The four credential fields, in the order `components/Configuration` L31-L68 declare them.
 *
 * `label` carries the trailing colon of the source label text and every lookup below matches it
 * exactly, so `Access Token:` resolves to one element rather than also matching
 * `Access Token Secret:`. `typedValue` is the value {@link EXPECTED_PAYLOAD} expects that field to
 * reach the request body under.
 */
const CREDENTIAL_FIELDS = [
  {
    label: 'API Key:',
    inputId: 'apiKey',
    inputType: 'text',
    typedValue: EXPECTED_PAYLOAD.apiKey,
  },
  {
    label: 'API Secret:',
    inputId: 'apiSecret',
    inputType: 'password',
    typedValue: EXPECTED_PAYLOAD.apiSecret,
  },
  {
    label: 'Access Token:',
    inputId: 'accessToken',
    inputType: 'text',
    typedValue: EXPECTED_PAYLOAD.accessToken,
  },
  {
    label: 'Access Token Secret:',
    inputId: 'accessTokenSecret',
    inputType: 'password',
    typedValue: EXPECTED_PAYLOAD.accessTokenSecret,
  },
] as const;

/** Value `getAttribute` reports for a bare boolean attribute, as L37/L47/L57/L67 declare `required`. */
const BOOLEAN_ATTRIBUTE_VALUE = '';

/** The two credential fields the subject renders unmasked. See ceiling 1 in the module docstring. */
const CLEAR_TEXT_FIELDS = CREDENTIAL_FIELDS.filter((field) => field.inputType === 'text');

/** The two it masks. Both are the `Secret`-suffixed halves of the pairs above. */
const MASKED_FIELDS = CREDENTIAL_FIELDS.filter((field) => field.inputType === 'password');

/**
 * Every attribute that would express an in-flight submit to a user or to assistive technology. The
 * subject sets none of them. See ceiling 2 in the module docstring.
 */
const PENDING_ATTRIBUTES = ['disabled', 'aria-busy', 'aria-disabled', 'aria-describedby'] as const;

/** Roles a pending indicator would be announced under. The subject renders none. */
const PENDING_ROLES = ['status', 'progressbar', 'alert'] as const;

/** Budget for a poll over state the submit request has to settle first. */
const SETTLE_TIMEOUT_MS = 10_000;

/** Placeholder for an evidence attachment a test produced nothing for. */
const NO_EVIDENCE = '(none)';

/* -------------------------------------------------------------------------- */
/* Recorded evidence                                                          */
/* -------------------------------------------------------------------------- */

/** One credential request a test below intercepted. */
interface RecordedSubmission {
  method: string;
  url: string;
  contentType: string | undefined;
  body: unknown;
}

/** One dialog the subject opened. */
interface RecordedDialog {
  type: string;
  message: string;
}

/* -------------------------------------------------------------------------- */
/* Attachment redaction                                                       */
/* -------------------------------------------------------------------------- */

/**
 * Characters of the digest an attachment carries in place of a value.
 *
 * Short on purpose: this is not a security control - the inputs are the fixed literals
 * of {@link EXPECTED_PAYLOAD} and are trivially recoverable from them - it exists only
 * so two runs of the same test can be compared without printing the values.
 */
const DIGEST_LENGTH = 12;

/** What a redacted field reports when the request carried no value for it. */
const ABSENT_VALUE = null;

/**
 * FNV-1a, 32-bit, hex. Chosen because it is four lines of arithmetic with no import:
 * `node:crypto` would work in the runner process but adds a dependency to a spec whose
 * only need is a stable short label.
 */
function digest(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0').slice(0, DIGEST_LENGTH);
}

/**
 * A credential-shaped body, reduced to what a report can carry safely.
 *
 * Keeps every key name, whether a value was present, its length, and a stable digest -
 * enough to see *which* field differs between two runs - and drops the value itself.
 * The values in this file are obvious test literals and no live secret is read anywhere
 * in this repository, so nothing here is exposed today. The reduction exists because CI
 * retains these reports for 30 days and a format that carries whole credential-shaped
 * bodies is one real fixture away from carrying a real one.
 *
 * The assertions are untouched: {@link EXPECTED_PAYLOAD} is still compared against the
 * intercepted body with full deep equality, in memory, and a mismatch still prints the
 * expected value in the failure diff - which is where that information belongs.
 *
 * @see docs/testing/DECISION-LOG.md - row D260.
 */
function redactBody(body: unknown): unknown {
  if (body === null || typeof body !== 'object' || Array.isArray(body)) {
    return body === undefined ? ABSENT_VALUE : { redacted: typeof body };
  }

  const reduced: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(body as Record<string, unknown>)) {
    if (typeof value !== 'string') {
      reduced[key] = { present: value !== undefined && value !== null, type: typeof value };
      continue;
    }
    reduced[key] = { present: value.length > 0, length: value.length, fnv1a: digest(value) };
  }
  return reduced;
}

/** A recorded submission with its body reduced by {@link redactBody}. */
function redactSubmission(submission: RecordedSubmission): Record<string, unknown> {
  return {
    method: submission.method,
    url: submission.url,
    contentType: submission.contentType,
    body: redactBody(submission.body),
  };
}

test.describe('harness route /configuration - TwitterAPISettings (frontend/src/components/Configuration)', () => {
  test('renders the Twitter API settings form with its four credential fields', async ({ page }) => {
    // Nothing declared to `browserDiagnostics`, which makes "this route renders cleanly" part of
    // the verdict: any console error or uncaught error fails the test at teardown.

    // The subject issues no request of its own: `components/Configuration` declares no mount effect.
    await page.goto(SETTINGS_ROUTE);

    const form = page.locator(SETTINGS_FORM);
    await expect(form).toBeVisible();

    await expect(
      form.getByRole('heading', {
        level: SETTINGS_HEADING_LEVEL,
        name: SETTINGS_HEADING,
        exact: true,
      }),
    ).toBeVisible();

    for (const field of CREDENTIAL_FIELDS) {
      const input = form.getByLabel(field.label, { exact: true });

      await expect(input).toBeVisible();

      // The element the label's `htmlFor` bound to, and the kind of field it is.
      await expect(input).toHaveAttribute('id', field.inputId);
      await expect(input).toHaveAttribute('type', field.inputType);
      await expect(input).toHaveAttribute('required', BOOLEAN_ATTRIBUTE_VALUE);
    }

    // Those four are the form's only fields.
    await expect(form.locator('input')).toHaveCount(CREDENTIAL_FIELDS.length);

    const saveButton = form.getByRole('button', { name: SAVE_BUTTON, exact: true });
    await expect(saveButton).toBeVisible();
    await expect(saveButton).toHaveAttribute('type', SAVE_BUTTON_TYPE);
  });

  test('posts the four typed credentials and confirms success in an alert', async ({ page }) => {
    const submissions: RecordedSubmission[] = [];
    const dialogs: RecordedDialog[] = [];
    const dialogFailures: string[] = [];

    // Nothing declared: a resolved submit reports success through `alert` alone, so the console
    // must stay clean on this path too.

    // Records every dialog the subject opens, then answers it. A failure to answer is recorded
    // here rather than thrown, because it happens outside the test's own call stack.
    page.on('dialog', async (dialog) => {
      dialogs.push({ type: dialog.type(), message: dialog.message() });
      await dialog
        .accept()
        .catch((error: Error) => dialogFailures.push(`dialog accept failed: ${error.message}`));
    });

    // Records what was sent, then answers with a status the stub resolves on.
    await page.route(CONFIG_ENDPOINT_GLOB, async (route) => {
      const request = route.request();

      submissions.push({
        method: request.method(),
        url: request.url(),
        contentType: request.headers()['content-type'],
        body: request.postDataJSON(),
      });

      await route.fulfill({ status: OK_STATUS, json: {} });
    });

    await page.goto(SETTINGS_ROUTE);

    try {
      // All four fields, each of which `components/Configuration` L37/L47/L57/L67 mark `required`.
      for (const field of CREDENTIAL_FIELDS) {
        await page.getByLabel(field.label, { exact: true }).fill(field.typedValue);
      }

      await page.getByRole('button', { name: SAVE_BUTTON, exact: true }).click();

      await expect
        .poll(() => submissions.length, {
          message: `expected exactly one ${CONFIG_ENDPOINT_METHOD} ${CONFIG_ENDPOINT_PATHNAME} request from one submit`,
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toBe(1);

      const submitted = submissions[0];

      expect(submitted.method).toBe(CONFIG_ENDPOINT_METHOD);
      expect(submitted.contentType).toBe(CONFIG_ENDPOINT_CONTENT_TYPE);

      // A relative URL, so the browser resolved it against the harness origin.
      const requested = new URL(submitted.url);
      expect(requested.origin).toBe(HARNESS_ORIGIN);
      expect(requested.pathname).toBe(CONFIG_ENDPOINT_PATHNAME);

      // Deep equality over the whole body: these four keys, these four values, nothing else.
      expect(submitted.body).toEqual(EXPECTED_PAYLOAD);

      await expect
        .poll(() => dialogs.map((dialog) => dialog.message), {
          message: 'expected one alert reporting the resolved submit',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toEqual([SUCCESS_ALERT]);

      expect(dialogs[0].type).toBe(ALERT_DIALOG);

      // Every dialog was answered, so no assertion above read a ledger a stuck dialog had frozen.
      expect(dialogFailures).toEqual([]);
    } finally {
      // Values redacted, keys and shape kept - see redactBody. The deep-equality
      // assertion above is the exact check; this attachment is the audit trail.
      await test.info().attach('credential-requests-redacted', {
        body: JSON.stringify(submissions.map(redactSubmission), null, 2),
        contentType: 'application/json',
      });
      await test.info().attach('dialogs', {
        body: JSON.stringify(dialogs, null, 2),
        contentType: 'application/json',
      });
      await test.info().attach('unanswered-dialogs', {
        body: dialogFailures.join('\n') || NO_EVIDENCE,
        contentType: 'text/plain',
      });
    }
  });

  test('reports failure in an alert when the config endpoint rejects', async ({
    page,
    browserDiagnostics,
  }) => {
    const submissions: RecordedSubmission[] = [];
    const dialogs: RecordedDialog[] = [];
    const dialogFailures: string[] = [];

    // Two records, and the only two tolerated: Chrome's own notice about the status this test
    // fulfils with, and L22's report of the rejection it caught.
    browserDiagnostics.allow(resourceFailure(REJECTED_STATUS), FAILURE_LOG);

    // Records every dialog the subject opens, then answers it.
    page.on('dialog', async (dialog) => {
      dialogs.push({ type: dialog.type(), message: dialog.message() });
      await dialog
        .accept()
        .catch((error: Error) => dialogFailures.push(`dialog accept failed: ${error.message}`));
    });

    // Records what was sent, then answers with a status the stub throws on.
    await page.route(CONFIG_ENDPOINT_GLOB, async (route) => {
      const request = route.request();

      submissions.push({
        method: request.method(),
        url: request.url(),
        contentType: request.headers()['content-type'],
        body: request.postDataJSON(),
      });

      await route.fulfill({ status: REJECTED_STATUS, json: {} });
    });

    await page.goto(SETTINGS_ROUTE);

    try {
      for (const field of CREDENTIAL_FIELDS) {
        await page.getByLabel(field.label, { exact: true }).fill(field.typedValue);
      }

      await page.getByRole('button', { name: SAVE_BUTTON, exact: true }).click();

      await expect
        .poll(() => dialogs.map((dialog) => dialog.message), {
          message: 'expected one alert reporting the rejected submit',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toEqual([FAILURE_ALERT]);

      expect(dialogs[0].type).toBe(ALERT_DIALOG);

      // The rejection reached the handler's own log, carrying the status the stub named.
      const reported = browserDiagnostics.errorText();
      expect(reported).toMatch(FAILURE_LOG);
      expect(reported).toMatch(REJECTED_STATUS_IN_LOG);

      // Caught rather than propagated: nothing escaped to the page and the route stays mounted.
      expect(browserDiagnostics.pageErrorText()).toBe('');
      await expect(
        page.getByRole('heading', {
          level: SETTINGS_HEADING_LEVEL,
          name: SETTINGS_HEADING,
          exact: true,
        }),
      ).toBeVisible();

      // The submit was attempted once, and the body it carried is the same on this path.
      expect(submissions).toHaveLength(1);
      expect(submissions[0].body).toEqual(EXPECTED_PAYLOAD);

      expect(dialogFailures).toEqual([]);
    } finally {
      // Same redaction as the success path: this body is identical on both, so leaving
      // it unredacted here would defeat redacting it there.
      await test.info().attach('credential-requests-redacted', {
        body: JSON.stringify(submissions.map(redactSubmission), null, 2),
        contentType: 'application/json',
      });
      await test.info().attach('dialogs', {
        body: JSON.stringify(dialogs, null, 2),
        contentType: 'application/json',
      });
      await test.info().attach('unanswered-dialogs', {
        body: dialogFailures.join('\n') || NO_EVIDENCE,
        contentType: 'text/plain',
      });
    }
  });

  test('renders the API key and the access token in clear text, and declares no autofill policy on any field', async ({
    page,
  }) => {
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

    // The subject issues no request of its own, and this test submits nothing.
    await page.goto(SETTINGS_ROUTE);

    try {
      const form = page.locator(SETTINGS_FORM);
      await expect(form).toBeVisible();

      /*
       * Filled with the values a real save would carry, so what is asserted below is the rendered
       * treatment of an actual credential rather than of an empty field.
       */
      for (const field of CREDENTIAL_FIELDS) {
        await form.getByLabel(field.label, { exact: true }).fill(field.typedValue);
      }

      /*
       * One read of every input in the form, so the whole treatment is a single exact oracle rather
       * than a sequence of polled attribute assertions. `null` is what `getAttribute` reports for an
       * absent attribute, which is how the missing `autocomplete` policy is expressed below.
       */
      const rendered = await form.evaluate((element) =>
        Array.from(element.querySelectorAll('input')).map((input) => ({
          id: input.getAttribute('id'),
          type: input.getAttribute('type'),
          autocomplete: input.getAttribute('autocomplete'),
          value: (input as HTMLInputElement).value,
        })),
      );

      /*
       * Those four inputs are the whole form, `API Key` and `Access Token` carry `type="text"` - so
       * each value is on screen exactly as typed, visible over a shoulder or in a screen share - and
       * no field declares an autofill policy, so the browser's default applies to all four. Both
       * unmasked fields are credentials: an API key and an access token authenticate exactly as their
       * secrets do.
       */
      expect(rendered).toEqual([
        { id: 'apiKey', type: 'text', autocomplete: null, value: EXPECTED_PAYLOAD.apiKey },
        { id: 'apiSecret', type: 'password', autocomplete: null, value: EXPECTED_PAYLOAD.apiSecret },
        {
          id: 'accessToken',
          type: 'text',
          autocomplete: null,
          value: EXPECTED_PAYLOAD.accessToken,
        },
        {
          id: 'accessTokenSecret',
          type: 'password',
          autocomplete: null,
          value: EXPECTED_PAYLOAD.accessTokenSecret,
        },
      ]);

      /*
       * The split, counted from that read: two unmasked and two masked. Asserted on the `type`
       * attribute rather than through a role query, because Playwright's role engine reports a
       * password input as a `textbox` while Testing Library's does not -
       * `frontend/src/components/Configuration.test.tsx` asserts the role-visible consequence at that
       * layer, and this one asserts the rendered treatment.
       */
      expect(rendered.filter((input) => input.type === 'text')).toHaveLength(
        CLEAR_TEXT_FIELDS.length,
      );
      expect(rendered.filter((input) => input.type === 'password')).toHaveLength(
        MASKED_FIELDS.length,
      );
    } finally {
      await test.info().attach('browser-diagnostics', {
        body: diagnostics.join('\n') || '(no console message and no page error)',
        contentType: 'text/plain',
      });
    }
  });

  test('expresses no pending state, so a second activation mid-flight issues a second credential write and a second dialog', async ({
    page,
  }) => {
    const submissions: RecordedSubmission[] = [];
    const dialogs: RecordedDialog[] = [];
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

    page.on('dialog', async (dialog) => {
      dialogs.push({ type: dialog.type(), message: dialog.message() });
      await dialog
        .accept()
        .catch((error: Error) => diagnostics.push(`dialog accept failed: ${error.message}`));
    });

    /**
     * Releases the writes this test is holding open, in registration order.
     *
     * Each entry resolves one intercepted request. Holding them is what makes the in-flight window
     * observable at all: answered immediately, the write would settle before a second activation
     * could be attempted.
     */
    const openWrites: Array<() => Promise<void>> = [];

    await page.route(CONFIG_ENDPOINT_GLOB, async (route) => {
      const request = route.request();

      submissions.push({
        method: request.method(),
        url: request.url(),
        contentType: request.headers()['content-type'],
        body: request.postDataJSON(),
      });

      await new Promise<void>((release) => {
        openWrites.push(async () => {
          release();
          await route.fulfill({ status: OK_STATUS, json: {} });
        });
      });
    });

    await page.goto(SETTINGS_ROUTE);

    try {
      for (const field of CREDENTIAL_FIELDS) {
        await page.getByLabel(field.label, { exact: true }).fill(field.typedValue);
      }

      const saveButton = page.getByRole('button', { name: SAVE_BUTTON, exact: true });

      await saveButton.click();

      await expect
        .poll(() => submissions.length, {
          message: 'expected the first submit to reach the intercepted endpoint',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toBe(1);

      /*
       * The write is open, and the control says nothing about it. Read in one evaluation rather than
       * as a sequence of polled negative assertions: `null` is what `getAttribute` reports for each
       * attribute the subject never sets.
       */
      await expect(saveButton).toBeEnabled();

      const pendingState = await page.locator(SETTINGS_FORM).evaluate(
        (form: HTMLFormElement, attributes: readonly string[]) => {
          const button = form.querySelector('button[type="submit"]');
          const read = (element: Element | null) =>
            Object.fromEntries(
              attributes.map((attribute) => [attribute, element?.getAttribute(attribute) ?? null]),
            );

          return { button: read(button), form: read(form) };
        },
        [...PENDING_ATTRIBUTES],
      );

      const noneSet = Object.fromEntries(PENDING_ATTRIBUTES.map((attribute) => [attribute, null]));

      expect(pendingState).toEqual({ button: noneSet, form: noneSet });

      /* Nor is any pending indicator rendered for a screen reader to announce. */
      for (const role of PENDING_ROLES) {
        await expect(page.getByRole(role)).toHaveCount(0);
      }

      /* No dialog yet: the alert is the first and only feedback, and it follows the write. */
      expect(dialogs).toEqual([]);

      /* Nothing stopped a second activation, and it issued its own write. */
      await saveButton.click();

      await expect
        .poll(() => submissions.length, {
          message: 'expected the second activation to issue its own credential write',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toBe(2);

      /* Both carried the same credentials to the same endpoint: duplicated, not coalesced. */
      expect(submissions.map((submission) => submission.body)).toEqual([
        EXPECTED_PAYLOAD,
        EXPECTED_PAYLOAD,
      ]);
      expect(new Set(submissions.map((submission) => submission.url)).size).toBe(1);

      for (const release of [...openWrites]) {
        await release();
      }

      /* And each opened its own dialog. */
      await expect
        .poll(() => dialogs.map((dialog) => dialog.message), {
          message: 'expected one alert per credential write',
          timeout: SETTLE_TIMEOUT_MS,
        })
        .toEqual([SUCCESS_ALERT, SUCCESS_ALERT]);
    } finally {
      for (const release of [...openWrites]) {
        await release().catch(() => undefined);
      }

      await test.info().attach('credential-requests', {
        body: JSON.stringify(submissions, null, 2),
        contentType: 'application/json',
      });
      await test.info().attach('dialogs', {
        body: JSON.stringify(dialogs, null, 2),
        contentType: 'application/json',
      });
      await test.info().attach('browser-diagnostics', {
        body: diagnostics.join('\n') || '(no console message and no page error)',
        contentType: 'text/plain',
      });
    }
  });

});

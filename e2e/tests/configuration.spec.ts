/**
 * End-to-end coverage of the harness client route `/configuration`.
 *
 * Subject: `TwitterAPISettings`, the default export of `frontend/src/components/Configuration`,
 * which `e2e/harness/main.tsx` L76 mounts at `/configuration` with no props. That module is an
 * extension-less file; `e2e/vite.harness.config.ts` resolves and transforms it, and redirects the
 * `@/services/configService` specifier it imports at L3 to `e2e/harness/stubs/configService.ts`.
 *
 * `test` and `expect` come from `./harness-fixtures`, whose automatic `noEgress` fixture aborts
 * every request addressed off the harness origin and fails the test at teardown for any harness
 * API request no route below claimed - `/api/config/twitter` being one of the three it names. Each
 * test therefore installs its own interception before navigating, and holds no state shared with
 * another test.
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
 *
 * The same component under Jest, with `updateTwitterAPIConfig` itself stubbed rather than its
 * transport intercepted, is covered by `frontend/src/components/Configuration.test.tsx`.
 *
 * @see e2e/README.md - adding a spec to this directory.
 * @see docs/testing/DECISION-LOG.md - the dialog-handling, branch-selection and payload-assertion
 *   rows for this file.
 */

import { expect, HARNESS_ORIGIN, test } from './harness-fixtures';

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
 */
const CONFIG_ENDPOINT_GLOB = '**/api/config/twitter';

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

/** Prefix this file records an uncaught page error under; no path of the subject produces one. */
const PAGE_ERROR = /pageerror:/;

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

/** Budget for a poll over state the submit request has to settle first. */
const SETTLE_TIMEOUT_MS = 10_000;

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

test.describe('harness route /configuration - TwitterAPISettings (frontend/src/components/Configuration)', () => {
  test('renders the Twitter API settings form with its four credential fields', async ({ page }) => {
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

    // The subject issues no request of its own: `components/Configuration` declares no mount effect.
    await page.goto(SETTINGS_ROUTE);

    try {
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
    } finally {
      await test.info().attach('browser-diagnostics', {
        body: diagnostics.join('\n') || '(no console message and no page error)',
        contentType: 'text/plain',
      });
    }
  });

  test('posts the four typed credentials and confirms success in an alert', async ({ page }) => {
    const submissions: RecordedSubmission[] = [];
    const dialogs: RecordedDialog[] = [];
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

    // Records every dialog the subject opens, then answers it.
    page.on('dialog', async (dialog) => {
      dialogs.push({ type: dialog.type(), message: dialog.message() });
      await dialog
        .accept()
        .catch((error: Error) => diagnostics.push(`dialog accept failed: ${error.message}`));
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
    } finally {
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

  test('reports failure in an alert when the config endpoint rejects', async ({ page }) => {
    const submissions: RecordedSubmission[] = [];
    const dialogs: RecordedDialog[] = [];
    const diagnostics: string[] = [];

    page.on('console', (message) => diagnostics.push(`console.${message.type()}: ${message.text()}`));
    page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));

    // Records every dialog the subject opens, then answers it.
    page.on('dialog', async (dialog) => {
      dialogs.push({ type: dialog.type(), message: dialog.message() });
      await dialog
        .accept()
        .catch((error: Error) => diagnostics.push(`dialog accept failed: ${error.message}`));
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
      const reported = diagnostics.join('\n');
      expect(reported).toMatch(FAILURE_LOG);
      expect(reported).toMatch(REJECTED_STATUS_IN_LOG);

      // Caught rather than propagated: nothing escaped to the page and the route stays mounted.
      expect(reported).not.toMatch(PAGE_ERROR);
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
    } finally {
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

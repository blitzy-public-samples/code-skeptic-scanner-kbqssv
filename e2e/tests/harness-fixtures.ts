/**
 * The `test` and `expect` every spec in `e2e/tests` imports.
 *
 * `e2e/playwright.config.ts` sets `testMatch` to the recursive `.spec.ts` glob, so this module is not
 * collected as a spec; it exists to extend Playwright's `test` with two automatic fixtures: one that
 * confines the browser to the harness and holds every spec to explicit request interception, and one
 * that turns the browser's own diagnostics into a verdict.
 *
 * The origin comes from `../vite.harness.config`, the same module the runner reads, so
 * a clone-specific port cannot make this fixture treat the real harness as external.
 *
 * ## What the isolation fixture enforces
 *
 * It registers one catch-all `context.route` rule, on the recursive wildcard glob, before the page
 * exists, so it covers that page, every other page opened in the context, popups and workers - the
 * three cases a per-spec `page.route` misses, the third being simply forgetting to install one.
 * Playwright evaluates route
 * handlers most-recently-registered-first and this rule is installed by an automatic fixture, so a
 * `page.route(...)` or `context.route(...)` a spec adds is matched first and wins. A request that
 * reaches this rule is therefore provably one no spec claimed, and it is dispositioned by origin:
 *
 * | Request | Disposition |
 * |---------|-------------|
 * | Not the harness origin | aborted `blockedbyclient`, recorded, thrown at teardown |
 * | Harness origin, a {@link CONTROL_PATH_PREFIX} path | aborted `blockedbyclient`, recorded, thrown at teardown |
 * | Harness origin, a {@link HARNESS_API_PATHS} path | passed to the dev server, which fails it closed, recorded, thrown at teardown |
 * | Harness origin, anything else | recorded as a census entry, then `route.fallback()` - documents, modules, assets |
 *
 * The third row is why the second exists. Falling through is right for the harness graph and wrong for a
 * dev-server control endpoint: those do filesystem and process work inside the Node process, which no
 * browser-level rule can contain, and the fallback used to carry them there without recording anything.
 * The census in the last row closes the other half of the same gap - what the harness served is now
 * attached to every test as evidence rather than left unrecorded.
 *
 * Both ledgers are read at teardown rather than in the request, because every caller in this
 * codebase swallows or replaces what it is handed, so a refusal expressed only as a response can be
 * absorbed and the test can still pass.
 *
 * ## Why every spec route must be anchored to the harness origin
 *
 * The rule above can only disposition a request that reaches it, and a `page.route(...)` a spec adds
 * is matched **first**. A host-agnostic pattern such as `'**\/tweets*'` therefore claims a request to
 * *any* origin that happens to share the path, and a spec handler that fulfils it turns a request
 * that left for a foreign host into a green assertion - the destination drift never reaches this
 * ledger. Every pattern in this directory is consequently spelled `` `${HARNESS_ORIGIN}/<path>` ``,
 * so a foreign origin falls through to the rule above and is aborted and recorded.
 * `e2e/tests/isolation.spec.ts` asserts that property for every path any spec here intercepts, using
 * {@link consumeAbortedRequestUrls} to acknowledge the refusal it provoked.
 *
 * @see docs/testing/DECISION-LOG.md - rows D130, D131 and D213.
 * ## What the diagnostics fixture enforces
 *
 * `browserDiagnostics` records every console message and every uncaught page error, attaches the whole
 * ledger to the test as evidence whatever the outcome, and **fails the test at teardown** for any
 * `console.error` or `pageerror` the test did not declare it expected.
 *
 * That last clause is the point. Recording diagnostics and attaching them proves nothing on its own: a
 * happy-path test that renders a heading passes just as well with a React teardown error and a rejected
 * promise in the console as without them, so an attachment nobody reads is not an assertion. Declaring
 * the expected records instead makes the *absence* of everything else part of every test's verdict, and
 * makes the expectation itself reviewable - each allow-list entry is a claim about what this route does
 * wrong today, sitting next to the assertion about what it does right.
 *
 * A test that expects a failure declares it with {@link BrowserDiagnostics.allow}, which is additive and
 * scoped to that test. A `console.warning`, `console.info` or `console.log` is recorded as evidence and
 * never fails a test: the dev server and React both emit notices that carry no verdict.
 *
 * @see docs/testing/DECISION-LOG.md - rows D130, D131 and D230.
 *
 * @example A route with no expected failure. Any console error fails the test.
 * ```ts
 * import { expect, HARNESS_ORIGIN, test } from './harness-fixtures';
 *
 * test('the feed renders', async ({ page }) => {
 *   await page.route(`${HARNESS_ORIGIN}/undefined/tweets*`, (route) => route.fulfill({ json: [] }));
 *   await page.goto('/');
 *   await expect(page.getByText('Real-Time Tweet Feed')).toBeVisible();
 * });
 * ```
 *
 * @example A route whose subject logs a caught failure. The one record is declared, and nothing else is
 * tolerated.
 * ```ts
 * test('the list reports its failed fetch', async ({ page, browserDiagnostics }) => {
 *   browserDiagnostics.allow(/Error fetching tweets:/);
 *   await page.goto('/tweets');
 *   await expect.poll(() => browserDiagnostics.errorText()).toMatch(/getTweets/);
 * });
 * ```
 */

import { test as base, expect } from '@playwright/test';

import { HARNESS_ORIGIN } from '../vite.harness.config';

export { HARNESS_ORIGIN };

/**
 * Pathnames the mounted components request, which `e2e/vite.harness.config.ts` answers
 * `503 harness-api-not-intercepted` when no spec has intercepted them.
 *
 * A spec drives one of these by installing its own route for it; reaching the dev server means it
 * did not. Keep in step with `HARNESS_API_SURFACE` in that config.
 *
 * This ledger is keyed by path and always was, so a request to one of these paths is recorded
 * whatever method it carries. The dev server's refusal is now keyed the same way (D410); before
 * that, a declared path under an undeclared method was recorded here as un-intercepted while the
 * SPA fallback had already answered it `200 text/html`.
 */
const HARNESS_API_PATHS: readonly string[] = Object.freeze([
  '/undefined/tweets',
  '/api/trends',
  '/api/config/twitter',
]);

/**
 * Prefix of every Vite dev-server control endpoint - the editor launcher, the inspector, the liveness
 * ping. Mirrors `CONTROL_PATH_PREFIX` in `e2e/vite.harness.config.ts`, which refuses the same prefix
 * server-side.
 *
 * Nothing in the harness graph is addressed under it: the entry document, the modules, the four
 * component files and the three API paths are all outside it. A same-origin request that carries it is
 * therefore never the application's, and it is the one class of same-origin request that must not be
 * allowed to fall through to the server - a control endpoint does filesystem and process work in Node,
 * where no browser-level rule reaches.
 */
const CONTROL_PATH_PREFIX = '/__';

/** Every URL aborted by {@link test}'s `noEgress` fixture, in the order they were seen. */
const abortedUrls: string[] = [];

/** Every same-origin control-path URL that fixture aborted, in the order they were seen. */
const deniedControlPathUrls: string[] = [];

/**
 * Every same-origin request that fixture let through to the dev server, in the order they were seen.
 *
 * A census rather than a verdict: the entry document, every module in the graph and every asset
 * legitimately arrive here. It is attached to the test as evidence so what the harness served is
 * readable after the fact, which is what the fallback branch used to leave unrecorded.
 */
const servedHarnessRequests: string[] = [];

/** Every harness API request that reached the dev server, in the order they were seen. */
const unInterceptedApiRequests: string[] = [];

/**
 * URLs the current test attempted that were not addressed to the harness.
 *
 * @returns A frozen snapshot, oldest first.
 */
export function abortedRequestUrls(): readonly string[] {
  return Object.freeze([...abortedUrls]);
}

/**
 * Harness API requests the current test issued without installing a route for them.
 *
 * @returns A frozen snapshot, oldest first, each entry `<METHOD> <url>`.
 */
export function unInterceptedApiRequestUrls(): readonly string[] {
  return Object.freeze([...unInterceptedApiRequests]);
}

/**
 * Reads the aborted-request ledger **and clears it**, so the refusal it records is asserted rather
 * than reported as a breach at teardown.
 *
 * Exists for one caller shape: a test whose subject *is* the refusal. `e2e/tests/isolation.spec.ts`
 * drives a foreign origin on a path a spec has a route for, to prove that the route does not claim
 * it and that this fixture aborts and records it instead. Consuming the entry is what lets that
 * proof reach teardown green.
 *
 * Consume only what the test provoked, and only after asserting it. An entry left in the ledger
 * still fails the test, so clearing one is meaningful only once the test has asserted the exact URL.
 *
 * @returns A frozen snapshot of the aborted URLs, oldest first, taken before the ledger was cleared.
 */
export function consumeAbortedRequestUrls(): readonly string[] {
  const seen = Object.freeze([...abortedUrls]);
  abortedUrls.length = 0;
  return seen;
}

/**
 * Reads the control-path ledger **and clears it**, so a test whose subject *is* that refusal can
 * assert it rather than have it reported as a breach at teardown.
 *
 * Same contract as {@link consumeAbortedRequestUrls}: consume only what the test deliberately caused,
 * and only after asserting the exact URL. `e2e/tests/isolation.spec.ts` is the one caller.
 *
 * @returns A frozen snapshot of the denied control-path URLs, oldest first, taken before clearing.
 */
export function consumeDeniedControlPathUrls(): readonly string[] {
  const seen = Object.freeze([...deniedControlPathUrls]);
  deniedControlPathUrls.length = 0;
  return seen;
}

/**
 * Every same-origin request the harness server answered for the current test, oldest first.
 *
 * @returns A frozen snapshot, each entry `<METHOD> <url>`.
 */
export function servedHarnessRequestUrls(): readonly string[] {
  return Object.freeze([...servedHarnessRequests]);
}

/**
 * Whether a same-origin URL addresses a dev-server control endpoint.
 *
 * @param url - Absolute request URL, already known to be same-origin.
 */
function isControlPathRequest(url: string): boolean {
  const { pathname } = new URL(url);
  return pathname.toLowerCase().startsWith(CONTROL_PATH_PREFIX);
}

/**
 * Whether a URL is one the harness itself serves.
 *
 * Same-origin only. A relative URL has already been resolved against `baseURL` by the time a route
 * handler sees it, so every legitimate harness request arrives absolute and on this origin.
 *
 * @param url - Absolute request URL as Playwright reports it.
 */
function isHarnessRequest(url: string): boolean {
  return url === HARNESS_ORIGIN || url.startsWith(`${HARNESS_ORIGIN}/`);
}

/**
 * Whether a harness-origin URL addresses one of {@link HARNESS_API_PATHS}.
 *
 * @param url - Absolute request URL, already known to be same-origin.
 */
function isHarnessApiRequest(url: string): boolean {
  const { pathname } = new URL(url);
  return HARNESS_API_PATHS.includes(pathname);
}

/**
 * One thing the browser reported: a console message, or an uncaught page error.
 *
 * `text` is the rendered form that appears in the attached evidence and that an allow-list pattern is
 * matched against, so a pattern can key on the `console.error:` / `pageerror:` prefix as well as on the
 * message.
 */
export interface BrowserRecord {
  /** `'console'` for a console message, `'pageerror'` for an uncaught error. */
  readonly kind: 'console' | 'pageerror';

  /** Whether this record fails the test when it is not allow-listed. */
  readonly failing: boolean;

  /** `console.<type>: <text>` or `pageerror: <message>`. */
  readonly text: string;
}

/** The handle a spec uses to declare what it expects and to read what was recorded. */
export interface BrowserDiagnostics {
  /**
   * Declares console errors and page errors this test expects, so they do not fail it.
   *
   * Additive and scoped to the calling test. Call it **before** navigating: a record that arrives
   * before its pattern is registered is still matched, because matching happens at teardown, but
   * declaring the expectation first keeps the test readable.
   *
   * @param patterns - Matched against {@link BrowserRecord.text}. Every failing record must match at
   *   least one of them.
   */
  allow(...patterns: RegExp[]): void;

  /** Every record so far, oldest first. */
  records(): readonly BrowserRecord[];

  /** Every record's text, newline-joined. Console notices included. */
  text(): string;

  /** Only the failing records' text, newline-joined: console errors and page errors. */
  errorText(): string;

  /** Only the uncaught page errors' text, newline-joined. */
  pageErrorText(): string;
}

/**
 * Allow-list pattern for the browser's own notice about a non-2xx response.
 *
 * Chrome writes one `console.error` reading `Failed to load resource: the server responded with a
 * status of <status> (<reason>)` for every response outside 200-299 a page receives. It comes from the
 * network stack rather than from any module under test, so a spec that *chooses* to fulfil a route with
 * a failing status has to declare it - and declares it with the status it chose, so a response arriving
 * with some other status still fails the test.
 *
 * @param status - The status the spec fulfilled with.
 * @returns A pattern matching that notice and no other.
 *
 * @example
 * ```ts
 * browserDiagnostics.allow(resourceFailure(500), /console\.error: Error fetching trend data:/);
 * await page.route(`${HARNESS_ORIGIN}/api/trends*`, (route) => route.fulfill({ status: 500, json: {} }));
 * ```
 */
export function resourceFailure(status: number): RegExp {
  return new RegExp(
    `console\\.error: Failed to load resource: the server responded with a status of ${status}\\b`,
  );
}

/**
 * Pattern matching Chrome's notice for a request the automatic `noEgress` fixture aborted.
 *
 * That fixture answers a foreign-origin request with `route.abort()`, and Chrome reports an aborted
 * request as a console error - so a spec that *provokes* the guard, rather than merely relying on it,
 * carries one error of its own making. `e2e/tests/isolation.spec.ts` is that spec: proving the guard
 * fires is its whole subject, so it declares this notice instead of being exempted from the verdict.
 *
 * @returns A pattern matching the abort notice and no other console error.
 *
 * @example
 * ```ts
 * browserDiagnostics.allow(blockedByEgressGuard());
 * ```
 */
export function blockedByEgressGuard(): RegExp {
  return /console\.error: Failed to load resource: net::ERR_BLOCKED_BY_CLIENT/;
}

export const test = base.extend<{
  noEgress: void;
  browserDiagnostics: BrowserDiagnostics;
}>({
  /**
   * Aborts every request to anything but the harness origin, and records every harness API request
   * no spec route claimed. Fails the test at teardown on either.
   *
   * `auto: true`, so a spec gets it without naming it, and it cannot be opted out of.
   */
  noEgress: [
    async ({ context }, use, testInfo) => {
      abortedUrls.length = 0;
      deniedControlPathUrls.length = 0;
      servedHarnessRequests.length = 0;
      unInterceptedApiRequests.length = 0;

      await context.route('**/*', async (route) => {
        const request = route.request();
        const url = request.url();

        if (!isHarnessRequest(url)) {
          abortedUrls.push(url);
          await route.abort('blockedbyclient');
          return;
        }

        // Same-origin, but a dev-server control endpoint rather than the application: aborted here and
        // refused again by the server-side guard, because reaching one means Node does filesystem or
        // process work on the browser's behalf. Ledgered either way, so it cannot pass silently.
        if (isControlPathRequest(url)) {
          deniedControlPathUrls.push(`${request.method()} ${url}`);
          await route.abort('blockedbyclient');
          return;
        }

        if (isHarnessApiRequest(url)) {
          unInterceptedApiRequests.push(`${request.method()} ${url}`);
        }

        // Everything else same-origin is the harness graph - the document, its modules, its assets.
        // Recorded before it is served, so the fallback branch leaves a census behind rather than
        // nothing at all.
        servedHarnessRequests.push(`${request.method()} ${url}`);
        await route.fallback();
      });

      await use();

      await testInfo.attach('harness-requests-served', {
        body: servedHarnessRequests.join('\n') || '(no same-origin request reached the harness)',
        contentType: 'text/plain',
      });

      const failures: string[] = [];

      if (abortedUrls.length > 0) {
        failures.push(
          `${abortedUrls.length} request(s) outside the harness origin ${HARNESS_ORIGIN}. Each was ` +
            'aborted, not performed. Mock the request with page.route(...) instead of letting it ' +
            `leave the browser:\n${abortedUrls.map((url) => `  - ${url}`).join('\n')}`,
        );
      }

      if (deniedControlPathUrls.length > 0) {
        failures.push(
          `${deniedControlPathUrls.length} request(s) to a dev-server control endpoint under ` +
            `${CONTROL_PATH_PREFIX}. Each was aborted, not performed. Nothing in the harness graph is ` +
            'addressed there, so such a request is either a mistake or an attempt to make the Node ' +
            `process act on the page's behalf:\n${deniedControlPathUrls
              .map((entry) => `  - ${entry}`)
              .join('\n')}`,
        );
      }

      if (unInterceptedApiRequests.length > 0) {
        failures.push(
          `${unInterceptedApiRequests.length} harness API request(s) reached the dev server, which ` +
            'answered 503 harness-api-not-intercepted. A flow that depends on one of these must ' +
            'install its own route and supply its own payload:\n' +
            unInterceptedApiRequests.map((entry) => `  - ${entry}`).join('\n'),
        );
      }

      if (failures.length > 0) {
        throw new Error(`${testInfo.title} breached harness isolation.\n${failures.join('\n')}`);
      }
    },
    { auto: true },
  ],

  /**
   * Records the browser's console and page errors, attaches them, and fails the test on any the test
   * did not declare.
   *
   * `auto: true`, so a spec that declares nothing still gets the enforcement; a spec that needs to
   * declare an expected failure, or to read what was recorded, names `browserDiagnostics` in its
   * arguments.
   *
   * Depends on `noEgress` explicitly, and names it before `page`, so the catch-all route is installed on
   * the context before the page this fixture listens to exists - the ordering `noEgress` documents.
   */
  browserDiagnostics: [
    async ({ noEgress, page }, use, testInfo) => {
      void noEgress;

      const records: BrowserRecord[] = [];
      const allowed: RegExp[] = [];

      page.on('console', (message) => {
        const type = message.type();
        records.push({
          kind: 'console',
          failing: type === 'error',
          text: `console.${type}: ${message.text()}`,
        });
      });

      page.on('pageerror', (error) => {
        records.push({ kind: 'pageerror', failing: true, text: `pageerror: ${error.message}` });
      });

      const render = (subset: readonly BrowserRecord[]): string =>
        subset.map((record) => record.text).join('\n');

      const diagnostics: BrowserDiagnostics = {
        allow(...patterns) {
          allowed.push(...patterns);
        },
        records() {
          return Object.freeze([...records]);
        },
        text() {
          return render(records);
        },
        errorText() {
          return render(records.filter((record) => record.failing));
        },
        pageErrorText() {
          return render(records.filter((record) => record.kind === 'pageerror'));
        },
      };

      await use(diagnostics);

      // Attached whatever the outcome, so a passing run still carries the evidence and a failing one
      // carries it alongside the failure.
      await testInfo.attach('browser-diagnostics', {
        body: render(records) || '(no console message and no page error)',
        contentType: 'text/plain',
      });

      const unexpected = records.filter(
        (record) => record.failing && !allowed.some((pattern) => pattern.test(record.text)),
      );

      if (unexpected.length > 0) {
        throw new Error(
          `${testInfo.title} produced ${unexpected.length} browser error(s) it did not declare. ` +
            'Either the route is broken, or the record is expected and belongs in a ' +
            'browserDiagnostics.allow(...) call in this test:\n' +
            `${unexpected.map((record) => `  - ${record.text}`).join('\n')}\n` +
            `Declared patterns: ${
              allowed.length === 0 ? '(none)' : allowed.map(String).join(', ')
            }`,
        );
      }
    },
    { auto: true },
  ],
});

export { expect };

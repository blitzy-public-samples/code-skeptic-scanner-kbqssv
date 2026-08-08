/**
 * The `test` and `expect` every spec in `e2e/tests` imports.
 *
 * `e2e/playwright.config.ts` sets `testMatch` to the recursive `.spec.ts` glob, so this module is not
 * collected as a spec; it exists to extend Playwright's `test` with one automatic fixture that confines
 * the browser to the harness and holds every spec to explicit request interception.
 *
 * The origin comes from `../harness-origin`, the same module the runner and the Vite config read, so
 * a clone-specific port cannot make this fixture treat the real harness as external.
 *
 * ## What the automatic fixture enforces
 *
 * It registers one catch-all `context.route` rule, on the recursive wildcard glob, before the page
 * exists, so it covers that page,
 * every other page opened in the context, popups and workers - the three cases a per-spec
 * `page.route` misses, the third being simply forgetting to install one. Playwright evaluates route
 * handlers most-recently-registered-first and this rule is installed by an automatic fixture, so a
 * `page.route(...)` or `context.route(...)` a spec adds is matched first and wins. A request that
 * reaches this rule is therefore provably one no spec claimed, and it is dispositioned by origin:
 *
 * | Request | Disposition |
 * |---------|-------------|
 * | Not the harness origin | aborted `blockedbyclient`, recorded, thrown at teardown |
 * | Harness origin, a {@link HARNESS_API_PATHS} path | passed to the dev server, which fails it closed, recorded, thrown at teardown |
 * | Harness origin, anything else | `route.fallback()` - documents, modules, assets |
 *
 * Both ledgers are read at teardown rather than in the request, because every caller in this
 * codebase swallows or replaces what it is handed, so a refusal expressed only as a response can be
 * absorbed and the test can still pass.
 *
 * @see docs/testing/DECISION-LOG.md - rows D130 and D131.
 *
 * @example
 * ```ts
 * import { expect, HARNESS_ORIGIN, test } from './harness-fixtures';
 *
 * test('the feed renders', async ({ page }) => {
 *   await page.route(`${HARNESS_ORIGIN}/undefined/tweets*`, (route) => route.fulfill({ json: [] }));
 *   await page.goto('/');
 *   await expect(page.getByText('Real-Time Tweet Feed')).toBeVisible();
 * });
 * ```
 */

import { test as base, expect } from '@playwright/test';

import { HARNESS_ORIGIN } from '../harness-origin';

export { HARNESS_ORIGIN };

/**
 * Pathnames the mounted components request, which `e2e/vite.harness.config.ts` answers
 * `503 harness-api-not-intercepted` when no spec has intercepted them.
 *
 * A spec drives one of these by installing its own route for it; reaching the dev server means it
 * did not. Keep in step with `HARNESS_API_SURFACE` in that config.
 */
const HARNESS_API_PATHS: readonly string[] = Object.freeze([
  '/undefined/tweets',
  '/api/trends',
  '/api/config/twitter',
]);

/** Every URL aborted by {@link test}'s `noEgress` fixture, in the order they were seen. */
const abortedUrls: string[] = [];

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

export const test = base.extend<{ noEgress: void }>({
  /**
   * Aborts every request to anything but the harness origin, and records every harness API request
   * no spec route claimed. Fails the test at teardown on either.
   *
   * `auto: true`, so a spec gets it without naming it, and it cannot be opted out of.
   */
  noEgress: [
    async ({ context }, use, testInfo) => {
      abortedUrls.length = 0;
      unInterceptedApiRequests.length = 0;

      await context.route('**/*', async (route) => {
        const request = route.request();
        const url = request.url();

        if (!isHarnessRequest(url)) {
          abortedUrls.push(url);
          await route.abort('blockedbyclient');
          return;
        }

        if (isHarnessApiRequest(url)) {
          unInterceptedApiRequests.push(`${request.method()} ${url}`);
        }

        await route.fallback();
      });

      await use();

      const failures: string[] = [];

      if (abortedUrls.length > 0) {
        failures.push(
          `${abortedUrls.length} request(s) outside the harness origin ${HARNESS_ORIGIN}. Each was ` +
            'aborted, not performed. Mock the request with page.route(...) instead of letting it ' +
            `leave the browser:\n${abortedUrls.map((url) => `  - ${url}`).join('\n')}`,
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
});

export { expect };

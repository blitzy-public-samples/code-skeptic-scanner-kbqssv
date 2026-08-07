/**
 * The `test` and `expect` every spec in `e2e/tests` imports.
 *
 * `e2e/playwright.config.ts` sets `testMatch: '**​/*.spec.ts'`, so this module is not collected as a
 * spec; it exists to extend Playwright's `test` with one automatic fixture that confines the browser
 * to the harness.
 *
 * ## Why a context-wide rule and not a per-spec `page.route`
 *
 * A spec's `page.route('**​/tweets*', ...)` covers the requests that spec anticipated, on the page
 * object it holds. Playwright documents two gaps in that: a page route does not intercept requests
 * a Service Worker makes, and it does not intercept a popup's very first request. A third gap is
 * simply forgetting - a new spec that installs no route has no interception at all, and its
 * component's mount-time fetch would go wherever its base URL points.
 *
 * `noEgress` closes all three by registering the rule on the **context**, before the page exists, so
 * it applies to that page, to every other page opened in the context, to popups, and to workers.
 * Anything not addressed to the harness origin is aborted. `serviceWorkers: 'block'` in the runner
 * config means no worker registers in the first place, and the Chromium switches there deny egress
 * below the route layer as well; this fixture is the layer that makes a refusal *attributable*, by
 * naming the URL in the test output.
 *
 * ## Order relative to a spec's own routes
 *
 * Playwright evaluates route handlers most-recently-registered first. This rule is installed by an
 * automatic fixture, before the test body runs, so a `page.route(...)` or `context.route(...)` the
 * spec adds is matched first and wins. Mocking a request is therefore unchanged; only a request no
 * handler claimed reaches this rule, and it is aborted rather than performed.
 *
 * @example
 * ```ts
 * import { expect, test } from './harness-fixtures';
 *
 * test('the feed renders', async ({ page }) => {
 *   await page.route('**​/tweets*', (route) => route.fulfill({ json: [] }));
 *   await page.goto('/');
 *   await expect(page.getByText('Real-Time Tweet Feed')).toBeVisible();
 * });
 * ```
 */

import { test as base, expect } from '@playwright/test';

/**
 * Origin the harness is served from, matching `server.host` and `server.port` in
 * `e2e/vite.harness.config.ts` and `baseURL` in `e2e/playwright.config.ts`.
 */
export const HARNESS_ORIGIN = 'http://127.0.0.1:4173';

/** Every URL aborted by {@link test}'s `noEgress` fixture, in the order they were seen. */
const abortedUrls: string[] = [];

/**
 * URLs the current test attempted that were not addressed to the harness.
 *
 * @returns A frozen snapshot, oldest first.
 */
export function abortedRequestUrls(): readonly string[] {
  return Object.freeze([...abortedUrls]);
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

export const test = base.extend<{ noEgress: void }>({
  /**
   * Aborts every request the context makes to anything but the harness origin.
   *
   * `auto: true`, so a spec gets it without naming it. Registered on the context rather than the
   * page, and before the test body runs, so a spec's own routes take precedence and this rule only
   * sees what nothing else claimed.
   */
  noEgress: [
    async ({ context }, use, testInfo) => {
      abortedUrls.length = 0;

      await context.route('**/*', async (route) => {
        const url = route.request().url();
        if (isHarnessRequest(url)) {
          await route.fallback();
          return;
        }
        abortedUrls.push(url);
        await route.abort('blockedbyclient');
      });

      await use();

      if (abortedUrls.length > 0) {
        const detail = abortedUrls.map((url) => `  - ${url}`).join('\n');
        throw new Error(
          `${testInfo.title} attempted ${abortedUrls.length} request(s) outside the harness ` +
            `origin ${HARNESS_ORIGIN}. Each was aborted, not performed:\n${detail}\n` +
            'Mock the request with page.route(...) instead of letting it leave the browser.',
        );
      }
    },
    { auto: true },
  ],
});

export { expect };

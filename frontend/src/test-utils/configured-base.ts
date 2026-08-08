/**
 * Loads a module graph with `REACT_APP_API_BASE_URL` set, so a suite can observe `services/api.ts` addressing
 * the backend's own paths instead of the unrouted `/undefined` prefix it emits by default.
 *
 * ## Why the module registry has to be discarded
 *
 * `frontend/src/services/api.ts` line 5 reads `process.env.REACT_APP_API_BASE_URL` **once, at module scope**,
 * into the constant it prefixes every request with. An assignment inside a test therefore changes nothing that
 * is observable: the module has already been evaluated, and its base URL is already the literal string
 * `undefined`. The variable has to be in place before the module is required, so
 * {@link importWithConfiguredBase} sets it, discards the registry and imports, in that order.
 *
 * ## What the caller gets, and what it does not
 *
 * The returned module - and everything it imports, including a second `axios` instance - is a **fresh**
 * instance, distinct from the one the test file imported at its top. Two consequences a caller has to know:
 *
 * - A `jest.spyOn(axios, …)` installed on the suite's own `axios` import does not affect the returned module.
 *   Drive these cases through msw instead, which intercepts at the transport the fresh instance also uses.
 * - Module state is not shared with the suite's own imports. Nothing in `services/` holds state, and
 *   `./handlers` and `./msw-server` are already loaded when this runs, so the request log and the msw server the
 *   suite asserts on are the same objects either way.
 *
 * ## Cleanup
 *
 * None is needed here and none is done here: the `afterEach` in `./setup-jest` deletes
 * `REACT_APP_API_BASE_URL` after every test, so the next test's subject reads it as unset again. That hook is
 * the single owner of the variable's lifecycle.
 *
 * @see frontend/src/test-utils/handlers.ts - `CONFIGURED_BASE_URL` and the handler set that answers the paths
 *   this base produces.
 * @see docs/testing/DECISION-LOG.md - why the seam is asserted under both base URLs rather than one.
 */

import { CONFIGURED_BASE_URL } from './handlers';

/**
 * Sets `REACT_APP_API_BASE_URL` to {@link CONFIGURED_BASE_URL}, discards the module registry and then runs
 * `load`, so every module `load` reaches reads the configured base::
 *
 *     const api = await importWithConfiguredBase(() => import('./api'));
 *     await expect(api.fetchTweets(2, 10)).rejects.toMatchObject({ response: { status: 500 } });
 *
 * `load` is a callback rather than a specifier string so the import stays a static-looking `import()` in the
 * calling file, which is what keeps the specifier resolving relative to that file and visible to the
 * transformer.
 *
 * @typeParam T - The module's shape, usually written as `typeof import('./api')`.
 * @param load - Imports the subject. Called after the variable is set and the registry is reset.
 * @returns Whatever `load` resolves to: the freshly evaluated module.
 */
export async function importWithConfiguredBase<T>(load: () => Promise<T>): Promise<T> {
  process.env.REACT_APP_API_BASE_URL = CONFIGURED_BASE_URL;
  jest.resetModules();
  return load();
}

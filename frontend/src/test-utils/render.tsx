/**
 * Shared render harness for the frontend Jest suites.
 *
 * Two named helpers, both published in `frontend/TESTING.md`:
 *
 * - `makeStore` - builds a Redux store wired from the tweet and config slices.
 * - `renderWithProviders` - mounts an element inside that store and a router.
 *
 * The store is assembled here from the *default* reducer exports of
 * `src/store/tweetSlice.ts` and `src/store/configSlice.ts`. This module does not
 * import `src/store/index.ts`: that module imports `{ tweetReducer }` and
 * `{ configReducer }`, which neither slice exports, so its reducer map is
 * `{ tweets: undefined, config: undefined }` and its `getState()` returns `{}`.
 * `src/store/index.test.ts` covers that behaviour, and `e2e/harness/main.tsx`
 * likewise assembles its own store.
 *
 * This module supplies no `api` and no `setupInterceptors`. `src/services/api.ts`
 * exports neither name, so under Jest the `api` binding inside `tweetSlice.ts`
 * stays `undefined` and its `fetchTweets` thunk settles through its own `catch`
 * branch. HTTP is intercepted by msw, which `src/test-utils/setup-jest.ts`
 * installs; nothing here mocks, stubs or wraps a transport.
 *
 * Nothing here intercepts `console`, and no error boundary is installed, so React
 * and Redux diagnostics reach the suites that assert on them.
 *
 * `renderWithProviders` receives a ready-made element, so the caller owns the
 * props that element carries. `TweetList` and `TrendCharts` list object props in
 * `useEffect` dependency arrays, so a suite hoists those objects to module scope;
 * an inline literal is a fresh reference on every render and refetches without
 * settling.
 *
 * Recorded design decisions: `docs/testing/DECISION-LOG.md`.
 */

import type { ReactElement, ReactNode } from 'react';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';
import type { RenderOptions, RenderResult } from '@testing-library/react';

import tweetReducer from '../store/tweetSlice';
import configReducer from '../store/configSlice';

/**
 * Slice reducer map backing every store this module builds.
 *
 * The two keys are `tweets` and `config`. They are the keys the application
 * itself reads: `src/pages/Dashboard.tsx` selects `state.tweets.tweets` and
 * `src/pages/Configuration.tsx` selects `state.config`. `e2e/harness/main.tsx`
 * registers the same two keys, so the Jest and Playwright layers observe one
 * state shape.
 *
 * Both members are the slices' default exports, which are their reducers.
 */
const sliceReducers = {
  tweets: tweetReducer,
  config: configReducer,
};

/** Type of {@link sliceReducers}, used to derive the state shape below. */
type SliceReducers = typeof sliceReducers;

/**
 * Fully resolved state of each slice in {@link sliceReducers}.
 *
 * A slice reducer returns its own state, so `ReturnType` yields that state
 * without either slice having to export its state interface - neither does.
 */
type SliceStates = { [K in keyof SliceReducers]: ReturnType<SliceReducers[K]> };

/**
 * Seed state accepted by {@link makeStore} and by {@link renderWithProviders}.
 *
 * Every slice key is optional, and each supplied slice may be partial, so a
 * suite can seed one field of one slice and leave the rest alone.
 *
 * Redux hands each entry straight to the matching slice reducer as its initial
 * state, so a supplied slice value *replaces* that slice's own initial state
 * rather than merging into it. A suite that needs the untouched fields to keep
 * their initial values supplies them alongside the ones it is changing.
 */
type PreloadedAppState = { [K in keyof SliceStates]?: Partial<SliceStates[K]> };

/**
 * Options accepted as the trailing argument of {@link renderWithProviders}.
 *
 * Every member is optional, so the two-argument call form documented in
 * `frontend/TESTING.md` remains a strict prefix of this signature.
 */
interface RenderWithProvidersOptions {
  /**
   * Seed state for the store this call builds. Ignored when `store` is supplied.
   */
  preloadedState?: PreloadedAppState;
  /**
   * An existing store to mount against, for a suite that dispatches before
   * rendering or that renders the same store twice. When omitted, a fresh store
   * is built for this call.
   */
  store?: AppStore;
  /**
   * Options forwarded to Testing Library's `render`, for example `container` or
   * `baseElement`. `wrapper` is excluded: the provider tree is always applied.
   */
  renderOptions?: Omit<RenderOptions, 'wrapper'>;
}

/**
 * Value returned by {@link renderWithProviders}: Testing Library's own result
 * plus the store the element was mounted against.
 */
type RenderWithProvidersResult = RenderResult & { store: AppStore };

/**
 * Builds a Redux store from the tweet and config slice reducers.
 *
 * A fresh store is returned on every call, so no state crosses between tests.
 * Middleware, enhancers and the devtools setting are left at `configureStore`'s
 * defaults, which are the defaults the application runs with. The serializability
 * check is therefore active. `tweetSchema` declares `timestamp` as `z.date()`, so
 * `makeTweet()` carries a real `Date`; dispatching one logs Redux Toolkit's
 * non-serializable-value warning and fails nothing.
 *
 * @param preloadedState - Optional seed state. Omit it to start each slice at its
 * own initial state: `tweets` at `{ tweets: [], status: 'idle', error: null }`
 * and `config` at `{ config: {}, status: 'idle', error: null }`.
 * @returns A configured store whose state is keyed by `tweets` and `config`.
 *
 * @example
 * const store = makeStore();
 * store.dispatch(addTweet(makeTweet()));
 * store.getState().tweets.tweets.length; // 1
 *
 * @example
 * const store = makeStore({ tweets: { tweets: [], status: 'loading', error: null } });
 * store.getState().tweets.status; // 'loading'
 */
export function makeStore(preloadedState?: PreloadedAppState) {
  return configureStore({
    reducer: sliceReducers,
    // The parameter above accepts a partial slice; `configureStore` types each
    // supplied slice as complete. This assertion widens the former to the latter.
    preloadedState: preloadedState as SliceStates | undefined,
  });
}

/**
 * The store type {@link makeStore} produces.
 *
 * This and {@link AppRootState} are the usable stand-ins for the `AppDispatch`
 * and `RootState` aliases exported by `src/store/index.ts`, which resolve to the
 * empty state of that module's invalid reducer map.
 */
export type AppStore = ReturnType<typeof makeStore>;

/** Root state of a store built by {@link makeStore}, keyed by `tweets` and `config`. */
export type AppRootState = ReturnType<AppStore['getState']>;

/**
 * Renders an element inside a Redux `Provider` and a `MemoryRouter`.
 *
 * The provider tree mirrors `src/app.tsx`, with the store outermost and the
 * router inside it. The router here is a `MemoryRouter`; the application mounts a
 * `BrowserRouter`. A suite therefore selects its entry route through the `route`
 * argument, and `window.history` is never read or written.
 *
 * The returned store is the one the element was mounted against, so a suite can
 * dispatch into it or read state back after an interaction.
 *
 * @param ui - The element to mount. Its props belong to the caller; object props
 * that a component lists in a `useEffect` dependency array are hoisted by the
 * suite, not defaulted here.
 * @param route - Initial router entry. Defaults to `'/'`.
 * @param options - Optional {@link RenderWithProvidersOptions}: `preloadedState`,
 * an existing `store`, and `renderOptions` forwarded to Testing Library.
 * @returns Testing Library's render result, extended with `store`.
 *
 * @example
 * const { store } = renderWithProviders(<TweetList filters={EMPTY_FILTERS} />);
 * expect(store.getState().tweets.status).toBe('idle');
 *
 * @example
 * renderWithProviders(
 *   <Routes>
 *     <Route path="/tweets" element={<TweetList filters={EMPTY_FILTERS} />} />
 *   </Routes>,
 *   '/tweets',
 * );
 */
export function renderWithProviders(
  ui: ReactElement,
  route: string = '/',
  options: RenderWithProvidersOptions = {},
): RenderWithProvidersResult {
  const { preloadedState, store = makeStore(preloadedState), renderOptions } = options;

  /**
   * Provider tree applied around `ui`. Passing it as Testing Library's `wrapper`
   * means `rerender` reapplies it to the replacement element.
   */
  const Providers = ({ children }: { children: ReactNode }) => (
    <Provider store={store}>
      <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
    </Provider>
  );

  // `wrapper` follows the spread, so a `renderOptions.wrapper` cannot displace it.
  return { store, ...render(ui, { ...renderOptions, wrapper: Providers }) };
}

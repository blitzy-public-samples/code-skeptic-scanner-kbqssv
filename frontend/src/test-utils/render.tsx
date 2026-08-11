/**
 * Shared render harness for the frontend Jest suites: `makeStore` builds a Redux store wired from the tweet
 * and config slices, and `renderWithProviders` mounts an element inside that store and a router.
 *
 * The store is assembled from the *default* reducer exports of the two slice modules, not from
 * `src/store/index.ts`, which this module does not import. Nothing here supplies `api` or
 * `setupInterceptors`, mocks a transport, intercepts `console` or installs an error boundary, so React and
 * Redux diagnostics reach the suites that assert on them.
 */

import type { ReactElement, ReactNode } from 'react';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';
import type { RenderOptions, RenderResult } from '@testing-library/react';

import tweetReducer from '../store/tweetSlice';
import configReducer from '../store/configSlice';

/** `tweets` and `config` are the keys the application's own selectors read. */
const sliceReducers = {
  tweets: tweetReducer,
  config: configReducer,
};

type SliceReducers = typeof sliceReducers;

/** Derived through `ReturnType` because neither slice exports its state interface. */
type SliceStates = { [K in keyof SliceReducers]: ReturnType<SliceReducers[K]> };

/**
 * Seed state for {@link makeStore} and {@link renderWithProviders}: every slice key is optional and each
 * supplied slice may be partial, so a suite can seed one field of one slice and leave the rest alone.
 *
 * `configureStore` hands each entry straight to the matching slice reducer as that slice's whole state, so
 * a partial passed through unaltered would leave the fields it omits `undefined`. {@link makeStore}
 * therefore merges each supplied partial onto the slice's own initial state, and the omitted fields keep
 * their initial values.
 */
type PreloadedAppState = { [K in keyof SliceStates]?: Partial<SliceStates[K]> };

/**
 * Dispatched only to read a slice reducer's initial state. No case reducer in either slice matches it, so
 * each reducer returns the state it was given - which for an `undefined` argument is its own
 * `initialState`. Neither slice exports that value, and this is how it is obtained without one.
 */
const INITIAL_STATE_PROBE = { type: '@@test-utils/probe-initial-state' };

/**
 * The initial state of every slice in {@link sliceReducers}, re-derived on each call rather than cached,
 * so the object a store is seeded from is never shared with an earlier store.
 */
function initialSliceStates(): SliceStates {
  return {
    tweets: sliceReducers.tweets(undefined, INITIAL_STATE_PROBE),
    config: sliceReducers.config(undefined, INITIAL_STATE_PROBE),
  };
}

/**
 * The complete per-slice state to seed a store with, or `undefined` when the caller supplied no seed at
 * all. Every slice is complete in the returned value: a partial the caller supplied is layered over that
 * slice's initial state, and a slice the caller did not mention is passed through at its initial state.
 */
function resolvePreloadedState(preloadedState?: PreloadedAppState): SliceStates | undefined {
  if (preloadedState === undefined) {
    return undefined;
  }

  const initial = initialSliceStates();

  return {
    tweets: { ...initial.tweets, ...preloadedState.tweets },
    config: { ...initial.config, ...preloadedState.config },
  };
}

interface RenderWithProvidersOptions {
  /** Seed state for the store this call builds. Ignored when `store` is supplied. */
  preloadedState?: PreloadedAppState;
  /** An existing store, for a suite that dispatches before rendering. Omitted means a fresh one. */
  store?: AppStore;
  /** Forwarded to Testing Library's `render`, minus `wrapper`: the provider tree always applies. */
  renderOptions?: Omit<RenderOptions, 'wrapper'>;
}

type RenderWithProvidersResult = RenderResult & { store: AppStore };

/**
 * Builds a Redux store from the two slice reducers, fresh on every call, so no state crosses between tests.
 * Middleware, enhancers and devtools stay at `configureStore`'s defaults, so the serializability check is
 * active: dispatching a `makeTweet()` fixture, whose `timestamp` is a `Date`, logs Redux Toolkit's warning
 * and fails nothing.
 *
 * @param preloadedState - Optional seed state, per slice and partial within each slice. Omit it to start
 * each slice at its own initial state; whatever a partial omits keeps its initial value, so seeding one
 * field never blanks the others.
 * @returns A configured store whose state is keyed by `tweets` and `config`.
 */
export function makeStore(preloadedState?: PreloadedAppState) {
  return configureStore({
    reducer: sliceReducers,
    preloadedState: resolvePreloadedState(preloadedState),
  });
}

export type AppStore = ReturnType<typeof makeStore>;

export type AppRootState = ReturnType<AppStore['getState']>;

/**
 * Renders an element inside a Redux `Provider` and a `MemoryRouter`, store outermost and router inside it as
 * in `src/app.tsx`. Where the application mounts a `BrowserRouter` this mounts a `MemoryRouter`, so a suite
 * selects its entry route through `route` and `window.history` is never touched.
 *
 * @returns Testing Library's result plus the `store` the element was mounted against.
 */
export function renderWithProviders(
  ui: ReactElement,
  route: string = '/',
  options: RenderWithProvidersOptions = {},
): RenderWithProvidersResult {
  const { preloadedState, store = makeStore(preloadedState), renderOptions } = options;

  // Passed as Testing Library's `wrapper`, so `rerender` reapplies the tree.
  const Providers = ({ children }: { children: ReactNode }) => (
    <Provider store={store}>
      <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
    </Provider>
  );

  // `wrapper` follows the spread and cannot be displaced.
  return { store, ...render(ui, { ...renderOptions, wrapper: Providers }) };
}

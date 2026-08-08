/**
 * The suite that pins the current behaviour of `./index`, the module the application builds its
 * Redux store in.
 *
 * `./index` imports `{ tweetReducer }` from `./tweetSlice` and `{ configReducer }` from
 * `./configSlice`. Neither slice exports either name - each exports its action creators as its only
 * named exports and its reducer as a `default` - so both specifiers resolve to `undefined`, and the
 * `reducer` map handed to `configureStore` is `{ tweets: undefined, config: undefined }`.
 *
 * Redux Toolkit routes a plain-object `reducer` to `combineReducers`, which copies only the values
 * that are functions into its final reducer set. That set is empty here, and five consequences
 * follow. Each is an oracle below, and each is a fact about `redux` 4.2.1 as installed:
 *
 * | Pinned behaviour                                | Mechanism                                          |
 * |-------------------------------------------------|----------------------------------------------------|
 * | construction does not throw                     | `assertReducerShape` iterates an empty set         |
 * | `console.error` reports the invalid reducer      | `reducerKeys.length === 0`, on every dispatch      |
 * | `getState()` is `{}` and never `undefined`       | `hasChanged` stays false, so `{}` is returned as-is|
 * | a dispatched slice action changes nothing        | the combination loop has no reducer to call        |
 * | the object is still a fully functional store     | `createStore` itself never fails                   |
 *
 * Two properties of that reporting shape the assertions. `console.error` receives more than one
 * message: `combineReducers` reports each filtered key first, so `No reducer provided for key
 * "tweets"` and the same for `"config"` precede the invalid-reducer report, which is therefore not
 * the first recorded call. And the report is emitted while `./index` is still evaluating, because
 * `index.ts` assigns `store = setupStore()` at module scope; `loadStoreModule` below loads the
 * module under a recorder that is already installed.
 *
 * @see frontend/src/store/index.ts - the module under test. This suite does not repair it, and the
 *   two unresolved reducer names are the subject rather than a defect in the suite.
 * @see frontend/src/test-utils/render.tsx - the shared render helper, which assembles its own store
 *   from the two slices' default reducer exports rather than importing this module.
 * @see frontend/TESTING.md - the frontend suite's conventions and the store-helper contract.
 * @see docs/testing/DECISION-LOG.md - row D34, and the rows covering how this suite loads its
 *   subject and matches the report text.
 */

/**
 * The part of the Redux store API these tests reflect on. Declared structurally: the store
 * `./index` builds mounts no reducer, so its state has no shape derived from either slice.
 */
interface ReflectedStore {
  dispatch: (action: { type: string; payload?: unknown }) => unknown;
  getState: () => Record<string, unknown>;
  subscribe: (listener: () => void) => () => void;
}

/**
 * The runtime exports of `./index`. `RootState` and `AppDispatch` are types on its last two lines
 * and are erased by the compiler, so they are absent here and absent from `Object.keys`.
 */
interface StoreModule {
  setupStore: () => ReflectedStore;
  store: ReflectedStore;
}

/**
 * The runtime export names `./index` carries, sorted. ts-jest emits
 * `exports.store = exports.setupStore = void 0`, so the insertion order is the reverse of this and
 * every comparison against this constant sorts first. `__esModule` is defined without `enumerable`
 * and so is correctly not a member.
 */
const EXPECTED_EXPORT_NAMES: readonly string[] = ['setupStore', 'store'];

/**
 * The leading clause of the report `redux` emits through `console.error` when its final reducer set
 * is empty. The clause that follows it in the full sentence names `combineReducers` and is not part
 * of the oracle.
 */
const INVALID_REDUCER_REPORT = 'Store does not have a valid reducer';

/** The two keys `./index` names in its `reducer` map, neither of which reaches the built store. */
const DECLARED_REDUCER_KEYS: readonly string[] = ['tweets', 'config'];

/** The type of a real action creator on `tweetSlice`: slice name `tweets`, reducer `addTweet`. */
const TWEET_SLICE_ACTION_TYPE = 'tweets/addTweet';

/**
 * Loads a fresh instance of `./index` through an isolated module registry.
 *
 * The whole module body re-runs on every call, including the `store = setupStore()` assignment on
 * its last executable line, so the reports described in the module docstring are emitted by this
 * call rather than by this file's own evaluation. Two calls produce two unrelated stores, so each
 * test below confines itself to the one instance it loads.
 */
function loadStoreModule(): StoreModule {
  let loaded!: StoreModule;

  // `jest.isolateModules` runs its callback synchronously, so `loaded` is assigned on return.
  jest.isolateModules(() => {
    loaded = require('./index');
  });

  return loaded;
}

/**
 * Replaces `console.error` with a silent recorder for the remainder of the test. Loading `./index`
 * emits three reports; with this installed they are recorded rather than printed. The `afterEach`
 * below puts the real function back.
 */
function recordConsoleError(): jest.SpyInstance {
  return jest.spyOn(console, 'error').mockImplementation(() => {});
}

/**
 * The first argument of every call the recorder captured. `redux` passes its reports as a single
 * string, so this is the full text of each one.
 */
function recordedMessages(recorder: jest.SpyInstance): string[] {
  return recorder.mock.calls.map((call) => String(call[0]));
}

describe('src/store/index.ts - the application store, whose two reducer imports resolve to undefined', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('loading the store module does not throw, because combineReducers discards the two undefined reducers instead of rejecting them', () => {
    recordConsoleError();

    expect(() => loadStoreModule()).not.toThrow();
  });

  test('Redux reports the invalid reducer through console.error while the store module is still evaluating', () => {
    const recorder = recordConsoleError();

    loadStoreModule();

    // Guards the search below against passing vacuously over an empty list of calls.
    expect(recorder).toHaveBeenCalled();
    expect(recordedMessages(recorder)).toEqual(
      expect.arrayContaining([expect.stringContaining(INVALID_REDUCER_REPORT)]),
    );
  });

  test('store.getState() returns an empty object rather than undefined, and carries neither of the two declared reducer keys', () => {
    recordConsoleError();

    const state = loadStoreModule().store.getState();

    expect(state).not.toBeUndefined();
    expect(state).toEqual({});
    expect(Object.keys(state)).toHaveLength(0);
    expect(state).not.toHaveProperty(DECLARED_REDUCER_KEYS[0]);
    expect(state).not.toHaveProperty(DECLARED_REDUCER_KEYS[1]);
  });

  test('the store module exports exactly setupStore and store at runtime, with RootState, AppDispatch and the two store hooks absent', () => {
    recordConsoleError();

    const exportNames = Object.keys(loadStoreModule()).sort();

    expect(exportNames).toEqual(EXPECTED_EXPORT_NAMES);
    // The last two lines of `index.ts` are type aliases, so the compiler leaves nothing behind.
    expect(exportNames).not.toContain('RootState');
    expect(exportNames).not.toContain('AppDispatch');
    // The hooks three `src/pages` modules import from this module, and which it has never exported.
    expect(exportNames).not.toContain('useAppDispatch');
    expect(exportNames).not.toContain('useAppSelector');
  });

  test('setupStore() is callable and returns a live store distinct from the one the module built at evaluation time', () => {
    recordConsoleError();

    const storeModule = loadStoreModule();
    const freshStore = storeModule.setupStore();

    expect(typeof storeModule.setupStore).toBe('function');
    expect(freshStore).not.toBe(storeModule.store);

    expect(typeof storeModule.store.dispatch).toBe('function');
    expect(typeof storeModule.store.getState).toBe('function');
    expect(typeof storeModule.store.subscribe).toBe('function');

    expect(typeof freshStore.dispatch).toBe('function');
    expect(typeof freshStore.getState).toBe('function');
    expect(typeof freshStore.subscribe).toBe('function');

    expect(freshStore.getState()).toEqual({});
  });

  test('dispatching a real tweetSlice action into the store is inert, because no reducer is mounted to receive it', () => {
    recordConsoleError();

    const { store } = loadStoreModule();

    store.dispatch({ type: TWEET_SLICE_ACTION_TYPE, payload: {} });

    expect(store.getState()).toEqual({});
    expect(store.getState()).not.toHaveProperty(DECLARED_REDUCER_KEYS[0]);
  });
});

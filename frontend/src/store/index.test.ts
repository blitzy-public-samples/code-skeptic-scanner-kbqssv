interface ReflectedStore {
  dispatch: (action: { type: string; payload?: unknown }) => unknown;
  getState: () => Record<string, unknown>;
  subscribe: (listener: () => void) => () => void;
}

interface StoreModule {
  setupStore: () => ReflectedStore;
  store: ReflectedStore;
}

const EXPECTED_EXPORT_NAMES: readonly string[] = ['setupStore', 'store'];

const INVALID_REDUCER_REPORT = 'Store does not have a valid reducer';

const DECLARED_REDUCER_KEYS: readonly string[] = ['tweets', 'config'];

const TWEET_SLICE_ACTION_TYPE = 'tweets/addTweet';

function loadStoreModule(): StoreModule {
  let loaded!: StoreModule;

  jest.isolateModules(() => {
    loaded = require('./index');
  });

  return loaded;
}

function recordConsoleError(): jest.SpyInstance {
  return jest.spyOn(console, 'error').mockImplementation(() => {});
}

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
    expect(exportNames).not.toContain('RootState');
    expect(exportNames).not.toContain('AppDispatch');
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

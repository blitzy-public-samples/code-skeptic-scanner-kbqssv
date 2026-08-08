/**
 * The suite that holds `./configSlice` to the behaviour it exhibits today.
 *
 * The slice is driven by calling its reducer directly - `reducer(previousState, actionCreator(payload))`.
 * No store is built here and `src/store/index.ts` is never imported.
 *
 * Every expectation below is an exact value taken from `./configSlice` itself - the three fields of its
 * `initialState` and the two literal status strings its reducers assign - or a payload one of these
 * tests supplies. Nothing here recomputes the reducer's spread to derive an expectation.
 *
 * Three properties of the subject shape these tests:
 *
 * 1. `updateConfig` **merges**: it spreads `action.payload` over the existing document instead of
 *    replacing it, so a member the payload does not name survives the call.
 * 2. That spread is **top level only**, so a payload that does name a member replaces that member's
 *    object whole - fields of it the payload omits are dropped, not carried over.
 * 3. `updateConfig` resets `error` to `null` on every call; `setError` never touches `config`.
 *
 * `Config` reaches `./configSlice` from `../schema/configSchema`, a specifier with no implementation in
 * this repository that `frontend/jest.config.js` maps to a test-side stub. It appears below in type
 * position only, so nothing here loads that stub at run time.
 *
 * @see frontend/src/store/configSlice.ts - the module under test.
 * @see frontend/src/test-utils/stubs/configSchema.ts - the `Config` shape these fixtures are built from.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for the "why" behind these choices,
 *   including row D34 on never importing `src/store/index.ts`.
 */

import type { Config } from '../test-utils/stubs/configSchema';

import reducer, { setError, updateConfig } from './configSlice';

/** The state shape `./configSlice` reduces. Declared locally: `./configSlice` does not export it. */
type ConfigState = {
  config: Config;
  status: string;
  error: string | null;
};

/** The reducer's second parameter, narrowed to what these tests hand it. */
type TestAction = { type: string; payload?: unknown };

/**
 * An action `./configSlice` declares no case for, so the reducer returns the state it was given. Built
 * fresh on every call; no action object is shared between tests.
 */
function makeUnhandledAction(): TestAction {
  return { type: 'unknown/action' };
}

/** The four `TwitterAPIConfig` fields. Fresh object on every call. */
function makeTwitterAPI(): NonNullable<Config['twitterAPI']> {
  return { apiKey: 'k', apiSecret: 's', accessToken: 't', accessTokenSecret: 'ts' };
}

/** A `ThresholdsConfig`. Fresh object on every call. */
function makeThresholds(): NonNullable<Config['thresholds']> {
  return { popularity: 100, doubtRating: 0.7 };
}

/** An `LLMConfig`. Fresh object on every call. */
function makeLLM(): NonNullable<Config['llm']> {
  return { engine: 'text-davinci-003', maxTokens: 60, temperature: 0.7 };
}

/**
 * A state whose document already carries two of the three `Config` members, at the status and error
 * `initialState` seeds. Fresh object graph on every call.
 */
function makeSeededState(): ConfigState {
  return {
    config: { twitterAPI: makeTwitterAPI(), thresholds: makeThresholds() },
    status: 'idle',
    error: null,
  };
}

/**
 * A structural copy of `value`, detached from it. Requires `value` to be JSON-representable, which
 * every fixture above is.
 */
function deepCopy<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

/**
 * The three fields of `initialState` and the value each is seeded with. Inert data: nothing writes to
 * this table or to anything reachable from it.
 */
const INITIAL_STATE_FIELDS: ReadonlyArray<{ field: keyof ConfigState; expected: unknown }> = [
  { field: 'config', expected: {} },
  { field: 'status', expected: 'idle' },
  { field: 'error', expected: null },
];

/** Payloads handed to `setError`, each recorded in `state.error` verbatim. Inert data. */
const SET_ERROR_PAYLOADS: ReadonlyArray<{ label: string; payload: string }> = [
  { label: 'a sentence naming the failure', payload: 'Configuration load failed' },
  { label: 'a bare token', payload: 'boom' },
  { label: 'the empty string', payload: '' },
];

describe('configSlice reducer', () => {
  describe('initial state', () => {
    it('returns its initial state for an action it declares no case for, carrying exactly three fields', () => {
      const state = reducer(undefined, makeUnhandledAction());

      expect(state).toEqual({ config: {}, status: 'idle', error: null });
      expect(Object.keys(state).sort()).toEqual(['config', 'error', 'status']);
    });

    it.each(INITIAL_STATE_FIELDS)('seeds $field with its documented initial value', ({ field, expected }) => {
      const state = reducer(undefined, makeUnhandledAction());

      expect(state[field]).toEqual(expected);
    });
  });

  describe('updateConfig', () => {
    it('sets status to "updated" and clears error to null', () => {
      const previous = reducer(undefined, makeUnhandledAction());

      const next = reducer(previous, updateConfig({ twitterAPI: makeTwitterAPI() }));

      expect(next.status).toBe('updated');
      expect(next.error).toBeNull();
    });

    it('spreads its payload into the empty document the initial state seeds', () => {
      const previous = reducer(undefined, makeUnhandledAction());

      const next = reducer(previous, updateConfig({ twitterAPI: makeTwitterAPI() }));

      expect(next.config).toEqual({
        twitterAPI: { apiKey: 'k', apiSecret: 's', accessToken: 't', accessTokenSecret: 'ts' },
      });
    });

    it('merges rather than replaces: a member the payload does not name survives, the named one takes the new value', () => {
      const previous = makeSeededState();

      const next = reducer(previous, updateConfig({ thresholds: { popularity: 250, doubtRating: 0.9 } }));

      // The payload named `thresholds` only, so `twitterAPI` is carried through untouched.
      expect(next.config.twitterAPI).toEqual({
        apiKey: 'k',
        apiSecret: 's',
        accessToken: 't',
        accessTokenSecret: 'ts',
      });
      expect(next.config.thresholds).toEqual({ popularity: 250, doubtRating: 0.9 });
    });

    it('replaces a named member whole rather than deep-merging the fields of it the payload omits', () => {
      const previous = makeSeededState();

      const next = reducer(previous, updateConfig({ twitterAPI: { apiKey: 'rotated' } }));

      // The spread is top level, so the three omitted `twitterAPI` fields do not survive.
      expect(next.config.twitterAPI).toEqual({ apiKey: 'rotated' });
      expect(next.config.thresholds).toEqual({ popularity: 100, doubtRating: 0.7 });
    });

    it('clears an error a previous setError recorded and returns status to "updated"', () => {
      const errored = reducer(undefined, setError('boom'));

      // The precondition the reset is measured against.
      expect(errored.error).toBe('boom');
      expect(errored.status).toBe('error');

      const next = reducer(errored, updateConfig({ llm: makeLLM() }));

      expect(next.error).toBeNull();
      expect(next.status).toBe('updated');
    });
  });

  describe('setError', () => {
    it.each(SET_ERROR_PAYLOADS)(
      'records $label in error verbatim and sets status to "error"',
      ({ payload }) => {
        const previous = reducer(undefined, makeUnhandledAction());

        const next = reducer(previous, setError(payload));

        expect(next.error).toBe(payload);
        expect(next.status).toBe('error');
      },
    );

    it('leaves the configuration document untouched', () => {
      const previous = makeSeededState();
      const documentBefore = deepCopy(previous.config);

      const next = reducer(previous, setError('Configuration save failed'));

      expect(next.config).toEqual(documentBefore);
      // Nothing assigned to `state.config`, so the document is carried through by reference.
      expect(next.config).toBe(previous.config);
    });
  });

  describe('the state handed to the reducer', () => {
    it('is not mutated by updateConfig, which returns a new state object', () => {
      const previous = makeSeededState();
      const previousBefore = deepCopy(previous);

      const next = reducer(previous, updateConfig({ thresholds: { popularity: 250 } }));

      expect(previous).toEqual(previousBefore);
      expect(next).not.toBe(previous);
    });

    it('is not mutated by setError, which returns a new state object', () => {
      const previous = makeSeededState();
      const previousBefore = deepCopy(previous);

      const next = reducer(previous, setError('Configuration save failed'));

      expect(previous).toEqual(previousBefore);
      expect(next).not.toBe(previous);
    });
  });
});

import type { Config } from '../test-utils/stubs/configSchema';

import reducer, { setError, updateConfig } from './configSlice';

type ConfigState = {
  config: Config;
  status: string;
  error: string | null;
};

type TestAction = { type: string; payload?: unknown };

function makeUnhandledAction(): TestAction {
  return { type: 'unknown/action' };
}

function makeTwitterAPI(): NonNullable<Config['twitterAPI']> {
  return { apiKey: 'k', apiSecret: 's', accessToken: 't', accessTokenSecret: 'ts' };
}

function makeThresholds(): NonNullable<Config['thresholds']> {
  return { popularity: 100, doubtRating: 0.7 };
}

function makeLLM(): NonNullable<Config['llm']> {
  return { engine: 'text-davinci-003', maxTokens: 60, temperature: 0.7 };
}

function makeSeededState(): ConfigState {
  return {
    config: { twitterAPI: makeTwitterAPI(), thresholds: makeThresholds() },
    status: 'idle',
    error: null,
  };
}

function deepCopy<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

const INITIAL_STATE_FIELDS: ReadonlyArray<{ field: keyof ConfigState; expected: unknown }> = [
  { field: 'config', expected: {} },
  { field: 'status', expected: 'idle' },
  { field: 'error', expected: null },
];

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

      expect(next.config.twitterAPI).toEqual({ apiKey: 'rotated' });
      expect(next.config.thresholds).toEqual({ popularity: 100, doubtRating: 0.7 });
    });

    it('clears an error a previous setError recorded and returns status to "updated"', () => {
      const errored = reducer(undefined, setError('boom'));

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

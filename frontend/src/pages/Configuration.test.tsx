/**
 * Suite over `frontend/src/pages/Configuration.tsx`, the configuration page. The group below is an ordinary
 * `describe`, so this module is collected and every specifier in it resolves on each run; every individual
 * test is marked `it.skip` and carries {@link BLOCKER} in its own title, which names the symbol that stops
 * the page rendering.
 *
 * `Configuration.tsx` L12 calls `useAppDispatch()`, imported at L4 from `@/store`. `frontend/src/store/index.ts`
 * exports `setupStore` (L5) and `store` (L15) at runtime and nothing else: its L17-18 exports are TypeScript
 * types, which are erased. The binding is therefore `undefined`, and calling it raises a `TypeError` naming
 * `useAppDispatch` before the component returns any element. L13's `useAppSelector` is never reached.
 *
 * Two further facts a maintainer un-skipping this suite meets:
 *
 * 1. `@/components/Configuration` default-exports one component, `TwitterAPISettings`, and exports none of the
 *    three names L2 imports, so the element types at L52, L56 and L60 are all `undefined`. The last case below
 *    records that export surface.
 * 2. L13 selects `state.config`, which is the config slice's whole state - `{ config, status, error }` - so the
 *    settings sit one level deeper at `state.config.config`, and L53, L57 and L61 read `undefined`. The bodies
 *    below assert that shape as it stands rather than a corrected one.
 *
 * The module graph itself loads: an absent named import binds `undefined` under the CommonJS emit rather than
 * raising, so this file is collectable and reports every case as skipped. `@/services/configService` has no
 * implementation under `src/services`; it resolves through the `moduleNameMapper` entry in
 * `frontend/jest.config.js` to `src/test-utils/stubs/configService.ts`, which is the collaborator boundary the
 * cases below drive.
 *
 * @see frontend/src/components/Configuration.test.tsx - the suite over the component module L2 imports from.
 * @see docs/testing/TRACEABILITY-MATRIX.md - gap G2, covering the page modules that cannot mount.
 */

import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import * as configurationComponents from '@/components/Configuration';
import Configuration from '@/pages/Configuration';
import { getConfig, updateConfig } from '@/services/configService';
import type { Config } from '@/test-utils/stubs/configSchema';
import { renderWithProviders } from '@/test-utils/render';

/*
 * Replaces the collaborator module the page reads and writes configuration through - a boundary beneath the
 * page, never the page itself. `@/components/Configuration` and `@/store` are left as they are.
 */
jest.mock('@/services/configService');

const getConfigMock = jest.mocked(getConfig);

/** Title of the group below, which is an ordinary `describe` so this module stays collected. */
const SUITE_TITLE = 'pages/Configuration (src/pages/Configuration.tsx)';

/**
 * Blocker suffixed onto every skipped test title below, so each `<testcase>` in
 * `frontend/reports/jest-junit.xml` carries the reason on the identity a result reader sees - Jest's
 * skip takes no reason argument, so the title is where one goes.
 *
 * It names the symbol that raises first: L12 runs before L13 reaches `useAppSelector` and before the
 * undefined child element types at L52, L56 and L60 are rendered.
 */
const BLOCKER =
  'BLOCKED: src/store/index.ts exports no useAppDispatch, so src/pages/Configuration.tsx line 12 ' +
  'raises TypeError: useAppDispatch is not a function';

/**
 * The configuration *service* function from `@/services/configService`, which `Configuration.tsx` L34 awaits.
 * Distinct from the config-slice action creator of the same name, which L5 imports under the alias
 * `updateConfigAction` and which reaches the store rather than the service.
 */
const updateConfigServiceMock = jest.mocked(updateConfig);

type User = ReturnType<typeof userEvent.setup>;

/** The loading view at `Configuration.tsx` L41-43, returned while the mount read is in flight. */
const LOADING_TEXT = 'Loading configuration...';

/** The `<h1>` at L51 and the container class at L50. */
const PAGE_HEADING = 'Configuration';
const PAGE_CONTAINER_CLASS = 'configuration-page';

/*
 * The error view at L45-47 renders `Error: {error}`, so its text content is the prefix followed by one of the
 * two fixed messages the page sets - L24 for a failed read, L37 for a failed write.
 */
const FETCH_FAILURE_TEXT = 'Error: Failed to fetch configuration';
const SAVE_FAILURE_TEXT = 'Error: Failed to update configuration';

/** Rejection messages the page discards: both handlers ignore the caught value and set a fixed string. */
const READ_REJECTION_MESSAGE = 'configuration read failed';
const WRITE_REJECTION_MESSAGE = 'configuration write failed';

/** `status` values `frontend/src/store/configSlice.ts` holds: L12 seeds `idle`, L22 sets `updated`. */
const STATUS_IDLE = 'idle';
const STATUS_UPDATED = 'updated';

/** The three keys of the config slice's state, sorted; the object L13 selects carries exactly these. */
const SLICE_STATE_KEYS = ['config', 'error', 'status'];

/** The three section keys L53, L57 and L61 read, sorted; also the three keys of a stored document. */
const SECTION_KEYS = ['llm', 'thresholds', 'twitterAPI'];

/** The names L2 imports and `@/components/Configuration` does not export. */
const CHILD_COMPONENT_NAMES = ['TwitterAPISettings', 'LLMSettings', 'ThresholdConfig'];

/** The document the collaborator resolves the mount read with. */
const FETCHED_CONFIG: Config = {
  twitterAPI: {
    apiKey: 'fetched-api-key',
    apiSecret: 'fetched-api-secret',
    accessToken: 'fetched-access-token',
    accessTokenSecret: 'fetched-access-token-secret',
  },
  llm: {
    engine: 'text-davinci-003',
    maxTokens: 150,
    temperature: 0.7,
  },
  thresholds: {
    popularity: 100,
    doubtRating: 0.7,
  },
};

/** The four values typed into the Twitter API section, and so the section its `onSave` emits. */
const EDITED_TWITTER_API = {
  apiKey: 'edited-api-key',
  apiSecret: 'edited-api-secret',
  accessToken: 'edited-access-token',
  accessTokenSecret: 'edited-access-token-secret',
};

/** Labels and submit control the Twitter API section renders. */
const FIELD_LABELS = {
  apiKey: 'API Key:',
  apiSecret: 'API Secret:',
  accessToken: 'Access Token:',
  accessTokenSecret: 'Access Token Secret:',
};

const TWITTER_API_SAVE_LABEL = 'Save Twitter API Settings';

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

/**
 * A promise with its resolution exposed, so a case can observe the page while the mount read is still in
 * flight without waiting on a timer.
 */
function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;

  const promise = new Promise<T>((resolveFn) => {
    resolve = resolveFn;
  });

  return { promise, resolve };
}

/** Settles once the mount read has resolved and the page body at L50-64 has replaced the loading view. */
async function waitForPageBody(): Promise<HTMLElement> {
  return screen.findByRole('heading', { level: 1, name: PAGE_HEADING });
}

/**
 * Fills the Twitter API section's four labelled inputs and submits it.
 *
 * `Configuration.tsx` L54 reaches `handleSave` only when the first child invokes the `onSave` prop it was
 * handed with the section it collected. Typing is wrapped in `act` because this dependency graph otherwise
 * schedules state updates outside React's act scope.
 */
async function fillAndSaveTwitterAPISection(user: User): Promise<void> {
  await act(async () => {
    await user.type(screen.getByLabelText(FIELD_LABELS.apiKey), EDITED_TWITTER_API.apiKey);
    await user.type(screen.getByLabelText(FIELD_LABELS.apiSecret), EDITED_TWITTER_API.apiSecret);
    await user.type(screen.getByLabelText(FIELD_LABELS.accessToken), EDITED_TWITTER_API.accessToken);
    await user.type(
      screen.getByLabelText(FIELD_LABELS.accessTokenSecret),
      EDITED_TWITTER_API.accessTokenSecret,
    );
  });

  await user.click(screen.getByRole('button', { name: TWITTER_API_SAVE_LABEL }));
}

describe(SUITE_TITLE, () => {
  beforeEach(() => {
    getConfigMock.mockReset();
    getConfigMock.mockResolvedValue(FETCHED_CONFIG);

    updateConfigServiceMock.mockReset();
    updateConfigServiceMock.mockImplementation(async (document) => ({ ...document }));
  });

  describe('the mount read', () => {
    it.skip(`shows the loading view, and nothing of the page body, while the read is in flight - ${BLOCKER}`, async () => {
      const pendingRead = deferred<Config>();

      getConfigMock.mockReturnValue(pendingRead.promise);

      const { store } = renderWithProviders(<Configuration />);

      expect(screen.getByText(LOADING_TEXT)).toBeInTheDocument();
      expect(screen.queryByRole('heading', { level: 1, name: PAGE_HEADING })).not.toBeInTheDocument();
      expect(screen.queryByText(FETCH_FAILURE_TEXT)).not.toBeInTheDocument();

      // Nothing has been dispatched yet, so the slice is still at the status L12 of configSlice.ts seeds.
      expect(store.getState().config).toHaveProperty('status', STATUS_IDLE);

      // Settles the read inside the case, so no state update lands after it ends.
      await act(async () => {
        pendingRead.resolve(FETCHED_CONFIG);
      });

      expect(await waitForPageBody()).toBeInTheDocument();
    });

    it.skip(`calls the configuration read exactly once, with no arguments - ${BLOCKER}`, async () => {
      renderWithProviders(<Configuration />);

      await waitForPageBody();

      expect(getConfigMock).toHaveBeenCalledTimes(1);
      expect(getConfigMock.mock.calls[0]).toHaveLength(0);
    });

    it.skip(`replaces the loading view with the page container and its heading once the read resolves - ${BLOCKER}`, async () => {
      const { container } = renderWithProviders(<Configuration />);

      const heading = await waitForPageBody();
      const page = container.querySelector(`.${PAGE_CONTAINER_CLASS}`);

      expect(page).not.toBeNull();
      expect(page).toContainElement(heading);
      expect(screen.queryByText(LOADING_TEXT)).not.toBeInTheDocument();
      expect(screen.queryByText(FETCH_FAILURE_TEXT)).not.toBeInTheDocument();
    });
  });

  describe('the document the read produced', () => {
    it.skip(`dispatches the fetched document into the config slice, which records it and the updated status - ${BLOCKER}`, async () => {
      const { store } = renderWithProviders(<Configuration />);

      await waitForPageBody();

      const sliceState = store.getState().config;

      expect(sliceState).toHaveProperty('config', FETCHED_CONFIG);
      expect(sliceState).toHaveProperty('status', STATUS_UPDATED);
      expect(sliceState).toHaveProperty('error', null);
    });

    it.skip(`hands all three child sections undefined: the selected object is the whole slice state - ${BLOCKER}`, async () => {
      const { store } = renderWithProviders(<Configuration />);

      await waitForPageBody();

      /* The object L13 selects: the slice state, not the stored document. */
      const selected = store.getState().config;

      expect(Object.keys(selected).sort()).toEqual(SLICE_STATE_KEYS);

      /* L53, L57 and L61 read these three keys off that object, and none of them is present on it. */
      SECTION_KEYS.forEach((section) => {
        expect(selected).not.toHaveProperty(section);
      });

      /* The sections are one level deeper, on the document the slice stores. */
      expect(Object.keys(selected.config).sort()).toEqual(SECTION_KEYS);
    });
  });

  describe('saving a section', () => {
    it.skip(`sends the service one document: the selected object merged with the edited section - ${BLOCKER}`, async () => {
      const user = userEvent.setup();

      renderWithProviders(<Configuration />);
      await waitForPageBody();

      await fillAndSaveTwitterAPISection(user);

      await waitFor(() => {
        expect(updateConfigServiceMock).toHaveBeenCalledTimes(1);
      });

      const [firstCall] = updateConfigServiceMock.mock.calls;

      expect(firstCall).toHaveLength(1);

      /*
       * L54 spreads the object L13 selected - the slice state - and overwrites one section, so the document
       * that leaves the page carries the slice's own three keys alongside the edited section.
       */
      const [sentDocument] = firstCall;

      expect(Object.keys(sentDocument).sort()).toEqual([...SLICE_STATE_KEYS, 'twitterAPI'].sort());
      expect(sentDocument).toHaveProperty('twitterAPI', EDITED_TWITTER_API);
      expect(sentDocument).toHaveProperty('config', FETCHED_CONFIG);
      expect(sentDocument).toHaveProperty('status', STATUS_UPDATED);
      expect(sentDocument).toHaveProperty('error', null);
    });

    it.skip(`dispatches that same document into the config slice and leaves the page mounted - ${BLOCKER}`, async () => {
      const user = userEvent.setup();

      const { store } = renderWithProviders(<Configuration />);
      await waitForPageBody();

      await fillAndSaveTwitterAPISection(user);

      await waitFor(() => {
        expect(store.getState().config.config).toHaveProperty('twitterAPI', EDITED_TWITTER_API);
      });

      const sliceState = store.getState().config;

      /* The slice keeps its own three keys; only the document it stores changed. */
      expect(Object.keys(sliceState).sort()).toEqual(SLICE_STATE_KEYS);
      expect(sliceState).toHaveProperty('status', STATUS_UPDATED);
      expect(sliceState).toHaveProperty('error', null);

      /*
       * L21 of configSlice.ts merges the payload into the stored document, so the document now carries the
       * three slice-state keys the page put in the payload as well as its own three sections.
       */
      expect(Object.keys(sliceState.config).sort()).toEqual(
        [...SECTION_KEYS, ...SLICE_STATE_KEYS].sort(),
      );
      expect(sliceState.config).toHaveProperty('llm', FETCHED_CONFIG.llm);
      expect(sliceState.config).toHaveProperty('thresholds', FETCHED_CONFIG.thresholds);

      expect(screen.getByRole('heading', { level: 1, name: PAGE_HEADING })).toBeInTheDocument();
      expect(screen.queryByText(SAVE_FAILURE_TEXT)).not.toBeInTheDocument();
    });
  });

  describe('failure disposition', () => {
    it.skip(`renders the fixed fetch-failure message and dispatches nothing when the read rejects - ${BLOCKER}`, async () => {
      getConfigMock.mockRejectedValue(new Error(READ_REJECTION_MESSAGE));

      const { store } = renderWithProviders(<Configuration />);

      expect(await screen.findByText(FETCH_FAILURE_TEXT)).toBeInTheDocument();

      /* L25 clears loading alongside L24's message, so the loading view does not survive the rejection. */
      expect(screen.queryByText(LOADING_TEXT)).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { level: 1, name: PAGE_HEADING })).not.toBeInTheDocument();

      /* The rejection message itself is discarded: L24 sets a fixed string. */
      expect(screen.queryByText(new RegExp(READ_REJECTION_MESSAGE))).not.toBeInTheDocument();

      /* The catch clause dispatches nothing, so the slice never leaves its seeded status. */
      expect(store.getState().config).toHaveProperty('status', STATUS_IDLE);
      expect(store.getState().config).toHaveProperty('error', null);
    });

    it.skip(`renders the fixed save-failure message and replaces the page when the write rejects - ${BLOCKER}`, async () => {
      updateConfigServiceMock.mockRejectedValue(new Error(WRITE_REJECTION_MESSAGE));

      const user = userEvent.setup();

      const { store } = renderWithProviders(<Configuration />);
      await waitForPageBody();

      await fillAndSaveTwitterAPISection(user);

      expect(await screen.findByText(SAVE_FAILURE_TEXT)).toBeInTheDocument();

      /*
       * L45 is reached because L32-39 never restores loading, so the error view takes the place of the page
       * body rather than sitting alongside it.
       */
      expect(screen.queryByText(LOADING_TEXT)).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { level: 1, name: PAGE_HEADING })).not.toBeInTheDocument();
      expect(screen.queryByText(new RegExp(WRITE_REJECTION_MESSAGE))).not.toBeInTheDocument();

      /* L35 is never reached, so the only document the slice holds is the one the mount read produced. */
      expect(store.getState().config).toHaveProperty('config', FETCHED_CONFIG);
      expect(store.getState().config).toHaveProperty('status', STATUS_UPDATED);
    });
  });

  describe('the child element types the page composes', () => {
    it.skip(`finds none of the three names on @/components/Configuration, which exports only a default - ${BLOCKER}`, () => {
      expect(Object.keys(configurationComponents)).toEqual(['default']);

      CHILD_COMPONENT_NAMES.forEach((name) => {
        expect(configurationComponents).not.toHaveProperty(name);
      });
    });
  });
});

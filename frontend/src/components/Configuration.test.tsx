/**
 * Contract of `frontend/src/components/Configuration`, whose default export is `TwitterAPISettings`: the form
 * it renders, the four controlled inputs it binds to its own state, the single object it hands its
 * collaborator on submit, and the disposition of a rejected save.
 *
 * Two properties of the subject are unusual, and both are handled in configuration rather than here. The
 * subject is an extension-less file: `frontend/jest.config.js` resolves `@/components/Configuration` to it
 * through `moduleNameMapper` and compiles it with `frontend/jest.transform.extensionless.js`, whose pattern is
 * `$`-anchored, so this suite's own `.tsx` name falls outside it and reaches ts-jest directly. And the
 * subject's collaborator specifier `@/services/configService` has no implementation under
 * `frontend/src/services`: the same config maps it to `frontend/src/test-utils/stubs/configService.ts`, which
 * is the module `jest.mock` below automocks.
 *
 * `frontend/src/test-utils/setup-jest.ts` supplies the jest-dom matchers and msw interception to every suite,
 * and registers no `alert` stub and no `console` spy; both are installed below, per test and restored. The
 * subject issues no request of its own, so msw stands over it as a guard only.
 *
 * @see frontend/src/components/Configuration - the module under test.
 * @see frontend/src/test-utils/render.tsx - the `renderWithProviders` harness every component suite mounts through.
 * @see frontend/TESTING.md - how to add a colocated suite, and the pitfalls of the four in this folder.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why each choice below is what it is.
 */

import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import TwitterAPISettings from '@/components/Configuration';
import { updateTwitterAPIConfig } from '@/services/configService';
import { renderWithProviders } from '@/test-utils/render';

jest.mock('@/services/configService');

/** The subject's only collaborator, automocked. Every test drives it from the default set in `beforeEach`. */
const updateTwitterAPIConfigMock = jest.mocked(updateTwitterAPIConfig);

/** The interaction session handle, as `userEvent.setup()` returns it. */
type User = ReturnType<typeof userEvent.setup>;

/** The four label texts the subject renders, in DOM order, each matched in full. */
const FIELD_LABELS = {
  apiKey: 'API Key:',
  apiSecret: 'API Secret:',
  accessToken: 'Access Token:',
  accessTokenSecret: 'Access Token Secret:',
};

/** Text of the subject's level-2 heading. */
const HEADING = 'Twitter API Settings';

/** Accessible name of the subject's only button. */
const SUBMIT_LABEL = 'Save Twitter API Settings';

/** One distinct value per field, so no assertion below can hold with two fields transposed. */
const CREDENTIALS = {
  apiKey: 'k-1',
  apiSecret: 's-2',
  accessToken: 't-3',
  accessTokenSecret: 'ts-4',
};

/** The keys, in order, of the object the subject builds for its collaborator. */
const PAYLOAD_KEYS = ['apiKey', 'apiSecret', 'accessToken', 'accessTokenSecret'];

/** What `test-utils/stubs/configService.ts` resolves with. The subject awaits it and reads nothing from it. */
const ACKNOWLEDGEMENT = { updated: true, section: 'twitterAPI' };

/** The subject's success message, its failure message, and the prefix it logs a failure under. */
const SUCCESS_ALERT = 'Twitter API settings updated successfully';
const FAILURE_ALERT = 'Failed to update Twitter API settings';
const FAILURE_LOG_PREFIX = 'Error updating Twitter API settings:';

/** Message of the rejection the failure test installs. */
const FAILURE_MESSAGE = 'save failed';

/** Label, `id` and `type` of each input the subject renders, in DOM order. */
const INPUT_FIELDS: [string, string, string][] = [
  [FIELD_LABELS.apiKey, 'apiKey', 'text'],
  [FIELD_LABELS.apiSecret, 'apiSecret', 'password'],
  [FIELD_LABELS.accessToken, 'accessToken', 'text'],
  [FIELD_LABELS.accessTokenSecret, 'accessTokenSecret', 'password'],
];

/**
 * Types every value in {@link CREDENTIALS} into the input its label identifies.
 *
 * `@testing-library/react` resolves `@testing-library/dom` 9.3.4 and `@testing-library/user-event` resolves
 * 10.4.1, so the `eventWrapper` the first configures is not the one the second reads, and each keystroke's
 * state update lands outside React's act scope. The keystrokes therefore run inside an explicit `act`, which
 * is where React expects them and what keeps the component-stack warning - one per character, each carrying a
 * source-mapped stack - out of the output and out of the suite's running time.
 */
async function fillCredentials(user: User): Promise<void> {
  await act(async () => {
    await user.type(screen.getByLabelText(FIELD_LABELS.apiKey), CREDENTIALS.apiKey);
    await user.type(screen.getByLabelText(FIELD_LABELS.apiSecret), CREDENTIALS.apiSecret);
    await user.type(screen.getByLabelText(FIELD_LABELS.accessToken), CREDENTIALS.accessToken);
    await user.type(
      screen.getByLabelText(FIELD_LABELS.accessTokenSecret),
      CREDENTIALS.accessTokenSecret,
    );
  });
}

/** Clicks the subject's submit button. */
async function submitForm(user: User): Promise<void> {
  await user.click(screen.getByRole('button', { name: SUBMIT_LABEL }));
}

describe('TwitterAPISettings (src/components/Configuration)', () => {
  /** jsdom implements no `alert`. Installed before every render, restored after every test. */
  let alertSpy: jest.SpyInstance;

  beforeEach(() => {
    updateTwitterAPIConfigMock.mockReset();
    updateTwitterAPIConfigMock.mockResolvedValue(ACKNOWLEDGEMENT);
    alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => undefined);
  });

  afterEach(() => {
    alertSpy.mockRestore();
  });

  it('renders the heading, the four labelled credential inputs and the submit button', () => {
    renderWithProviders(<TwitterAPISettings />);

    expect(screen.getByRole('heading', { level: 2, name: HEADING })).toBeInTheDocument();
    expect(screen.getByLabelText(FIELD_LABELS.apiKey)).toBeInTheDocument();
    expect(screen.getByLabelText(FIELD_LABELS.apiSecret)).toBeInTheDocument();
    expect(screen.getByLabelText(FIELD_LABELS.accessToken)).toBeInTheDocument();
    expect(screen.getByLabelText(FIELD_LABELS.accessTokenSecret)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: SUBMIT_LABEL })).toBeInTheDocument();

    // Two of the four inputs are `type="password"`, which carries no role.
    expect(screen.getAllByRole('textbox')).toHaveLength(2);
  });

  it.each(INPUT_FIELDS)(
    'renders the "%s" field as an empty required input with id "%s" and type "%s"',
    (label, id, type) => {
      renderWithProviders(<TwitterAPISettings />);

      const input = screen.getByLabelText(label);

      expect(input).toHaveAttribute('id', id);
      expect(input).toHaveAttribute('type', type);
      expect(input).toBeRequired();
      expect(input).toHaveValue('');
    },
  );

  it('binds each labelled input to its own piece of component state', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TwitterAPISettings />);

    await fillCredentials(user);

    expect(screen.getByLabelText(FIELD_LABELS.apiKey)).toHaveValue(CREDENTIALS.apiKey);
    expect(screen.getByLabelText(FIELD_LABELS.apiSecret)).toHaveValue(CREDENTIALS.apiSecret);
    expect(screen.getByLabelText(FIELD_LABELS.accessToken)).toHaveValue(CREDENTIALS.accessToken);
    expect(screen.getByLabelText(FIELD_LABELS.accessTokenSecret)).toHaveValue(
      CREDENTIALS.accessTokenSecret,
    );
  });

  it('hands the collaborator one object carrying the four entered credentials, untransformed', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TwitterAPISettings />);

    await fillCredentials(user);
    await submitForm(user);

    await waitFor(() => {
      expect(updateTwitterAPIConfigMock).toHaveBeenCalledTimes(1);
    });
    expect(updateTwitterAPIConfigMock).toHaveBeenCalledWith(CREDENTIALS);

    const [firstCall] = updateTwitterAPIConfigMock.mock.calls;

    expect(firstCall).toHaveLength(1);
    expect(Object.keys(firstCall[0])).toEqual(PAYLOAD_KEYS);
  });

  it('alerts the success message once the save resolves', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TwitterAPISettings />);

    await fillCredentials(user);
    await submitForm(user);

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(SUCCESS_ALERT);
    });
    expect(alertSpy).toHaveBeenCalledTimes(1);
  });

  it('prevents the browser default on submit, so the page is never reloaded', async () => {
    const { container } = renderWithProviders(<TwitterAPISettings />);
    const form = container.querySelector('form');

    expect(form).not.toBeNull();

    /*
     * Dispatching `submit` on the form reaches the handler with all four fields still empty, because it skips
     * the constraint-validation step that the submit algorithm behind a button click performs - the step the
     * last test in this file covers. `fireEvent` returns false when a listener called `preventDefault`.
     */
    expect(fireEvent.submit(form as HTMLFormElement)).toBe(false);

    // Settles the handler inside the test, so no `alert` arrives after the spy is restored.
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(SUCCESS_ALERT);
    });
  });

  it('logs the error, alerts the failure and leaves the form mounted when the save rejects', async () => {
    const failure = new Error(FAILURE_MESSAGE);

    updateTwitterAPIConfigMock.mockRejectedValue(failure);

    const user = userEvent.setup();

    renderWithProviders(<TwitterAPISettings />);
    await fillCredentials(user);

    // The subject's own logging is this test's assertion target, so the spy covers the submit alone: it goes
    // in once the form is filled and comes out immediately after.
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);

    try {
      await submitForm(user);

      await waitFor(() => {
        expect(alertSpy).toHaveBeenCalledWith(FAILURE_ALERT);
      });

      expect(consoleError).toHaveBeenCalledTimes(1);
      expect(consoleError).toHaveBeenCalledWith(FAILURE_LOG_PREFIX, expect.any(Error));

      const [logCall] = consoleError.mock.calls;

      expect(logCall).toHaveLength(2);
      expect(logCall[1]).toBe(failure);
      expect((logCall[1] as Error).message).toBe(FAILURE_MESSAGE);

      expect(alertSpy).toHaveBeenCalledTimes(1);
      expect(alertSpy).not.toHaveBeenCalledWith(SUCCESS_ALERT);

      // Swallowed rather than propagated: the form, and the values entered into it, are both still there.
      expect(screen.getByRole('heading', { level: 2, name: HEADING })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: SUBMIT_LABEL })).toBeInTheDocument();
      expect(screen.getByLabelText(FIELD_LABELS.apiKey)).toHaveValue(CREDENTIALS.apiKey);
    } finally {
      consoleError.mockRestore();
    }
  });

  it('does not reach the collaborator while a required credential is still empty', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TwitterAPISettings />);

    /*
     * `handleSubmit` validates nothing of its own, so the four `required` attributes are the entire guard: the
     * submit algorithm a button click runs stops at the first invalid control and never dispatches the event.
     */
    await submitForm(user);

    expect(screen.getByLabelText(FIELD_LABELS.apiKey)).toBeInvalid();
    expect(updateTwitterAPIConfigMock).not.toHaveBeenCalled();
    expect(alertSpy).not.toHaveBeenCalled();
  });
});

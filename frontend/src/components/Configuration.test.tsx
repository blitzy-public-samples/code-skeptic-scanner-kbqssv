/**
 * The suite for `TwitterAPISettings`, the default export of
 * `frontend/src/components/Configuration`.
 *
 * Two properties of the implemented form are pinned here as **ceilings**, not fixed. Both would need
 * an edit to `frontend/src/components/Configuration`, which is production code this programme is not
 * authorized to change - the two authorized touches are both in `backend/`. Each is recorded in
 * `frontend/TESTING.md`, `docs/testing/TRACEABILITY-MATRIX.md` §G and the suggested-next-tasks lists,
 * and the cases at the end of this file assert them so that closing either becomes a deliberate,
 * test-visible change.
 *
 * ## 1. The submit has no pending state
 *
 * L11-L25 `handleSubmit` is `async` and awaits `updateTwitterAPIConfig`, but the component holds no
 * state for the in-flight call. The L70 button is never `disabled`, never carries `aria-busy`, and
 * neither does the form; no spinner or status text is rendered. Nothing therefore prevents a second
 * activation while the first write is still open, and the consequence is not cosmetic: each
 * activation issues its **own** credential write and opens its **own** `alert`. A screen-reader user
 * is additionally told nothing at all between the click and the dialog.
 *
 * ## 2. Two of the four credential fields are rendered in clear text
 *
 * L31-L38 render `API Key` and L51-L58 render `Access Token` as `type="text"`, so both values are
 * visible on screen, readable over a shoulder or in a screen share, and offered to the browser's
 * autofill and password managers as ordinary text. Only the two `Secret`-suffixed fields are
 * `type="password"`. No field declares an `autocomplete` policy either, so the browser's default
 * applies to all four. The masking is therefore driven by the field's *name*, not by whether the
 * value is a secret - an API key and an access token are credentials exactly as their secrets are.
 *
 * @see frontend/src/components/Configuration - the module under test.
 * @see e2e/tests/configuration.spec.ts - the same two ceilings characterised in a real browser.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why these are recorded, not fixed.
 */

import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import TwitterAPISettings from '@/components/Configuration';
import { updateTwitterAPIConfig } from '@/services/configService';
import { renderWithProviders } from '@/test-utils/render';

jest.mock('@/services/configService');

const updateTwitterAPIConfigMock = jest.mocked(updateTwitterAPIConfig);

type User = ReturnType<typeof userEvent.setup>;

const FIELD_LABELS = {
  apiKey: 'API Key:',
  apiSecret: 'API Secret:',
  accessToken: 'Access Token:',
  accessTokenSecret: 'Access Token Secret:',
};

const HEADING = 'Twitter API Settings';

const SUBMIT_LABEL = 'Save Twitter API Settings';

const CREDENTIALS = {
  apiKey: 'k-1',
  apiSecret: 's-2',
  accessToken: 't-3',
  accessTokenSecret: 'ts-4',
};

const PAYLOAD_KEYS = ['apiKey', 'apiSecret', 'accessToken', 'accessTokenSecret'];

const ACKNOWLEDGEMENT = { updated: true, section: 'twitterAPI' };

const SUCCESS_ALERT = 'Twitter API settings updated successfully';
const FAILURE_ALERT = 'Failed to update Twitter API settings';
const FAILURE_LOG_PREFIX = 'Error updating Twitter API settings:';

const FAILURE_MESSAGE = 'save failed';

const INPUT_FIELDS: [string, string, string][] = [
  [FIELD_LABELS.apiKey, 'apiKey', 'text'],
  [FIELD_LABELS.apiSecret, 'apiSecret', 'password'],
  [FIELD_LABELS.accessToken, 'accessToken', 'text'],
  [FIELD_LABELS.accessTokenSecret, 'accessTokenSecret', 'password'],
];

/** The two credential fields the subject renders unmasked. See ceiling 2 in the module docstring. */
const CLEAR_TEXT_FIELDS = [FIELD_LABELS.apiKey, FIELD_LABELS.accessToken] as const;

/** The two it masks. Both are the `Secret`-suffixed halves of the pairs above. */
const MASKED_FIELDS = [FIELD_LABELS.apiSecret, FIELD_LABELS.accessTokenSecret] as const;

/**
 * Every attribute that would express an in-flight submit to a user or to assistive technology. The
 * subject sets none of them on the button or the form. See ceiling 1 in the module docstring.
 */
const PENDING_ATTRIBUTES = ['disabled', 'aria-busy', 'aria-disabled', 'aria-describedby'] as const;

/** Roles a pending indicator would be announced under. The subject renders none. */
const PENDING_ROLES = ['status', 'progressbar', 'alert'] as const;

/** Wrap typing in act because this dependency graph otherwise schedules state updates outside React's act scope. */
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

async function submitForm(user: User): Promise<void> {
  await user.click(screen.getByRole('button', { name: SUBMIT_LABEL }));
}

describe('TwitterAPISettings (src/components/Configuration)', () => {
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

    /* fireEvent.submit bypasses native constraint validation; its false return records preventDefault. */
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

    // Scope the console spy to the rejected submit so unrelated logs are not captured.
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

    /* The required attributes are the only validation; a button click blocks submit before the handler runs. */
    await submitForm(user);

    expect(screen.getByLabelText(FIELD_LABELS.apiKey)).toBeInvalid();
    expect(updateTwitterAPIConfigMock).not.toHaveBeenCalled();
    expect(alertSpy).not.toHaveBeenCalled();
  });

  it('expresses no pending state while the credential write is in flight, so the control stays live', async () => {
    /* A write this test holds open, which is the only way to observe the form mid-submit. */
    let resolveWrite: (acknowledgement: typeof ACKNOWLEDGEMENT) => void = () => undefined;
    const inFlight = new Promise<typeof ACKNOWLEDGEMENT>((resolve) => {
      resolveWrite = resolve;
    });

    updateTwitterAPIConfigMock.mockReturnValue(inFlight);

    const user = userEvent.setup();
    const { container } = renderWithProviders(<TwitterAPISettings />);

    await fillCredentials(user);
    await submitForm(user);

    await waitFor(() => {
      expect(updateTwitterAPIConfigMock).toHaveBeenCalledTimes(1);
    });

    const button = screen.getByRole('button', { name: SUBMIT_LABEL });
    const form = container.querySelector('form');

    /* The write is open, and neither the control nor the form says so. */
    expect(button).toBeEnabled();
    for (const attribute of PENDING_ATTRIBUTES) {
      expect(button).not.toHaveAttribute(attribute);
      expect(form).not.toHaveAttribute(attribute);
    }

    /* Nor is any pending indicator rendered for a screen reader to announce. */
    for (const role of PENDING_ROLES) {
      expect(screen.queryByRole(role)).toBeNull();
    }

    /* No dialog yet either: the alert is the first and only feedback, and it comes after the write. */
    expect(alertSpy).not.toHaveBeenCalled();

    await act(async () => {
      resolveWrite(ACKNOWLEDGEMENT);
      await inFlight;
    });

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(SUCCESS_ALERT);
    });
  });

  it('issues a second credential write and a second alert when the still-live control is activated again mid-flight', async () => {
    const writes: Array<(acknowledgement: typeof ACKNOWLEDGEMENT) => void> = [];

    updateTwitterAPIConfigMock.mockImplementation(
      () =>
        new Promise<typeof ACKNOWLEDGEMENT>((resolve) => {
          writes.push(resolve);
        }),
    );

    const user = userEvent.setup();
    renderWithProviders(<TwitterAPISettings />);

    await fillCredentials(user);

    /* Two activations of a control that was never disabled between them. */
    await submitForm(user);
    await waitFor(() => expect(updateTwitterAPIConfigMock).toHaveBeenCalledTimes(1));
    await submitForm(user);
    await waitFor(() => expect(updateTwitterAPIConfigMock).toHaveBeenCalledTimes(2));

    /* Each carried the same credentials to the same endpoint: the write is duplicated, not coalesced. */
    expect(updateTwitterAPIConfigMock.mock.calls[0][0]).toEqual(CREDENTIALS);
    expect(updateTwitterAPIConfigMock.mock.calls[1][0]).toEqual(CREDENTIALS);

    await act(async () => {
      writes.forEach((resolve) => resolve(ACKNOWLEDGEMENT));
      await Promise.resolve();
    });

    /* And each opened its own dialog. */
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledTimes(2);
    });
    expect(alertSpy.mock.calls).toEqual([[SUCCESS_ALERT], [SUCCESS_ALERT]]);
  });

  it('renders the API key and the access token in clear text, masking only the secret-suffixed fields', () => {
    renderWithProviders(<TwitterAPISettings />);

    /*
     * `type="text"`, so the value is on screen as typed. Both are credentials: an API key and an
     * access token authenticate exactly as their secrets do.
     */
    for (const label of CLEAR_TEXT_FIELDS) {
      expect(screen.getByLabelText(label)).toHaveAttribute('type', 'text');
    }

    for (const label of MASKED_FIELDS) {
      expect(screen.getByLabelText(label)).toHaveAttribute('type', 'password');
    }

    /*
     * Two of four reachable as textboxes is the observable consequence: `type="password"` carries no
     * role, so only the unmasked pair answers a role query.
     */
    const textboxes = screen.getAllByRole('textbox');

    expect(textboxes).toHaveLength(CLEAR_TEXT_FIELDS.length);
    expect(textboxes.map((input) => input.getAttribute('id'))).toEqual(['apiKey', 'accessToken']);

    /* And no field states an autofill policy, so the browser's default applies to all four. */
    for (const label of Object.values(FIELD_LABELS)) {
      expect(screen.getByLabelText(label)).not.toHaveAttribute('autocomplete');
    }
  });
});

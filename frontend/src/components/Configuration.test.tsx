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
});

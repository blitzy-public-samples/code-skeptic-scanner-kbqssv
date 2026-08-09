"""Contract tests for the three isolation guarantees ``backend/tests/conftest.py`` makes.

Subject
-------
The test infrastructure itself, not an ``app`` module. Every other suite in this
tree rests on three promises made by ``conftest.py``, and each of them was once
true only in the common case:

Secrets are never printed
    A settings-normalisation failure fires precisely when a **real** credential
    has reached a settings singleton, and its message is written to stdout and
    into ``reports/junit.xml`` -- artifacts that get archived, uploaded and pasted
    into tickets. A message that interpolated the value would publish the secret
    it exists to warn about, so :func:`tests.conftest.describe_unexpected_value`
    reports the shape of a credential instead of the credential.

A loopback port is authorized only while this process holds it
    :func:`tests.conftest._is_local_address` admits a loopback target only on a
    port this process bound itself. That claim has to expire when the socket
    closes: the operating system may hand the number to anything that asks next,
    and a registry that only grew would keep authorizing it -- so the suite could
    reach a neighbouring checkout's dev server through a recycled port.

A child process is refused in every phase, not only inside a test
    A subprocess owns its own sockets, so no other guard in ``conftest.py`` can
    see what it does. Refusal is therefore decided by *what is being run*, from
    :func:`tests.conftest.pytest_configure` -- which is before collection --
    through the last teardown, rather than by whether a test happens to be
    executing.

How the phase probes work
-------------------------
Two of the phases these tests are about are phases in which no test is running,
so neither can be asserted from inside a test body:

* the **collection** probe runs at this module's own scope, which pytest
  evaluates while collecting, and records the outcome in
  :data:`COLLECTION_TIME_PROBE` for a test to read afterwards;
* the **teardown** probe runs in a fixture finalizer and asserts there. A failed
  assertion in a finalizer is reported as an error against the test that used the
  fixture, so the check is enforced without any test depending on another test's
  side effects.

Both probes name a command that exists nowhere. If the guard were absent the
attempt would raise ``FileNotFoundError`` rather than start anything, and the
probe records that as an unexpected outcome, so a missing guard fails loudly and
a passing run never spawns a process.

Scope
-----
This module imports no ``app`` module. It opens loopback sockets it binds and
closes itself, which is exactly the traffic the guard is designed to permit.

@see docs/testing/DECISION-LOG.md - rows D105, D121, D223, D224 and D225.
"""

import os
import socket
import subprocess
from types import SimpleNamespace

import pytest

from tests.conftest import (
    ALLOWED_CHILD_PROCESS_COMMANDS,
    REQUIRED_SETTINGS_ENV,
    SENSITIVE_SETTINGS_FIELDS,
    TESTABILITY_SETTINGS_VALUES,
    UnmockedNetworkAccessError,
    _assert_settings_are_synthetic,
    _is_port_owned_by_this_process,
    _settings_normalisation_failures,
    child_process_command,
    describe_expected_value,
    describe_unexpected_value,
    is_allowed_child_process,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Oracles.
# --------------------------------------------------------------------------- #

#: Stands in for a real credential that has leaked into the process. It is not a
#: credential of anything: the point is only that no message may echo it.
SENTINEL_SECRET = "blitzy-sentinel-not-a-real-credential-2f8c41d9"

#: Loopback address the port-ownership cases bind and connect on.
LOOPBACK_ADDRESS = "127.0.0.1"

#: A command no filesystem carries. Used by both phase probes, so that a run in
#: which the guard is missing raises ``FileNotFoundError`` instead of executing
#: anything.
UNRUNNABLE_COMMAND = "blitzy-guard-contract-probe-no-such-executable"

#: Fragment every :class:`tests.conftest.UnmockedNetworkAccessError` carries.
REFUSAL_FRAGMENT = "attempted an unmocked network call"

#: The two guarded entry points, each probed in each phase. Both are covered
#: because they are installed by different builders -- a construction guard on
#: ``subprocess.Popen.__init__`` and a call guard on ``os.system`` -- so a
#: regression in one would be invisible in a probe that only exercised the other.
PROBE_ENTRY_POINTS = ("subprocess.Popen", "os.system")

#: Subject the guard reports for a refusal raised outside any test.
COLLECTION_SUBJECT = "collection"

#: Recorded when a probe was permitted rather than refused.
PERMITTED = "PERMITTED"

#: Prefix recorded when a probe ended in some third way -- the shape a missing
#: guard produces, since the command cannot be found.
UNEXPECTED_PREFIX = "UNEXPECTED"


def _attempt(entry_point):
    """Attempt one refused child process and report how the attempt ended.

    :param entry_point: One of :data:`PROBE_ENTRY_POINTS`.
    :returns: The refusal message, :data:`PERMITTED` if the spawn was allowed
        through, or an :data:`UNEXPECTED_PREFIX` description of any other
        outcome.
    """
    try:
        if entry_point == "subprocess.Popen":
            subprocess.Popen([UNRUNNABLE_COMMAND])
        else:
            os.system(UNRUNNABLE_COMMAND)
    except UnmockedNetworkAccessError as refusal:
        return str(refusal)
    except BaseException as unexpected:  # pragma: no cover - guard is installed
        return "{prefix} {name}: {detail}".format(
            prefix=UNEXPECTED_PREFIX,
            name=type(unexpected).__name__,
            detail=unexpected,
        )
    return PERMITTED  # pragma: no cover - guard is installed


def _probe_child_processes():
    """Attempt both guarded entry points and report each outcome by name."""
    return {entry_point: _attempt(entry_point) for entry_point in PROBE_ENTRY_POINTS}


def _assert_was_refused(outcomes, phase):
    """Assert every outcome in ``outcomes`` is a refusal naming its entry point."""
    assert sorted(outcomes) == sorted(PROBE_ENTRY_POINTS)
    for entry_point, outcome in sorted(outcomes.items()):
        assert outcome != PERMITTED, (
            "{entry_point} was permitted during {phase}; the guard must refuse "
            "every command outside "
            "tests.conftest.ALLOWED_CHILD_PROCESS_COMMANDS in every "
            "phase".format(entry_point=entry_point, phase=phase)
        )
        assert not outcome.startswith(UNEXPECTED_PREFIX), (
            "the {phase} probe of {entry_point} did not reach the guard at all, "
            "which means the guard was not installed: {outcome}".format(
                phase=phase, entry_point=entry_point, outcome=outcome
            )
        )
        assert REFUSAL_FRAGMENT in outcome
        assert entry_point in outcome
        assert UNRUNNABLE_COMMAND in outcome


#: Outcome of a child-process attempt at each guarded entry point, made while
#: pytest was **collecting** this module. Read by
#: :func:`test_child_process_is_refused_during_collection`.
COLLECTION_TIME_PROBE = _probe_child_processes()


# --------------------------------------------------------------------------- #
# F24 -- a failure message never discloses a credential.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field_name", sorted(SENSITIVE_SETTINGS_FIELDS))
def test_sensitive_field_description_withholds_the_value(field_name):
    """Every sensitive field is described by shape rather than by value."""
    described = describe_unexpected_value(field_name, SENTINEL_SECRET)

    assert SENTINEL_SECRET not in described
    assert "value withheld" in described
    # The shape is still reported, which is what makes the failure actionable.
    assert str(len(SENTINEL_SECRET)) in described
    assert "str" in described


@pytest.mark.parametrize("field_name", sorted(SENSITIVE_SETTINGS_FIELDS))
def test_sensitive_field_expectation_is_named_by_reference(field_name):
    """No message pairs a credential field with a credential-shaped literal."""
    described = describe_expected_value(field_name)
    placeholder = REQUIRED_SETTINGS_ENV.get(field_name)

    assert "backend/tests/conftest.py" in described
    if placeholder is not None:
        assert placeholder not in described


def test_sensitive_description_of_an_absent_value_says_so():
    """``None`` is reported as absent, not as a zero-length string."""
    assert describe_unexpected_value("NOTION_API_KEY", None) == "absent (None)"


def test_two_different_secrets_receive_different_fingerprints():
    """A fingerprint distinguishes two wrong values without disclosing either."""
    first = describe_unexpected_value("SECRET_KEY", SENTINEL_SECRET)
    second = describe_unexpected_value("SECRET_KEY", SENTINEL_SECRET + "-other")

    assert first != second


def test_the_same_secret_receives_the_same_fingerprint():
    """So two messages naming one fingerprint refer to one value."""
    assert describe_unexpected_value(
        "SECRET_KEY", SENTINEL_SECRET
    ) == describe_unexpected_value("SECRET_KEY", SENTINEL_SECRET)


def test_non_sensitive_field_description_still_shows_the_value():
    """A threshold or a collection name is diagnostic, so it is not withheld."""
    described = describe_unexpected_value("ALLOWED_ORIGINS", ["https://example.test"])

    assert described == repr(["https://example.test"])
    assert describe_expected_value("ALLOWED_ORIGINS") == repr(
        TESTABILITY_SETTINGS_VALUES["ALLOWED_ORIGINS"]
    )


def _settings_carrying(**overrides):
    """Return a settings stand-in holding every expected value, then ``overrides``."""
    values = dict(REQUIRED_SETTINGS_ENV)
    values.update(TESTABILITY_SETTINGS_VALUES)
    values["NOTION_API_KEY"] = None
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "field_name", sorted(SENSITIVE_SETTINGS_FIELDS & set(REQUIRED_SETTINGS_ENV))
)
def test_normalisation_failure_message_withholds_a_leaked_secret(field_name):
    """The message the readiness gate raises names the field and nothing else."""
    failures = _settings_normalisation_failures(
        _settings_carrying(**{field_name: SENTINEL_SECRET})
    )

    assert len(failures) == 1
    assert field_name in failures[0]
    assert SENTINEL_SECRET not in failures[0]


@pytest.mark.parametrize(
    "field_name", sorted(SENSITIVE_SETTINGS_FIELDS & set(REQUIRED_SETTINGS_ENV))
)
def test_singleton_assertion_message_withholds_a_leaked_secret(field_name):
    """And so does the session-scoped assertion over the live singletons."""
    with pytest.raises(AssertionError) as excinfo:
        _assert_settings_are_synthetic(
            _settings_carrying(**{field_name: SENTINEL_SECRET}),
            "probe.settings",
        )

    reported = str(excinfo.value)

    assert field_name in reported
    assert SENTINEL_SECRET not in reported


def test_singleton_assertion_message_withholds_a_leaked_notion_key():
    """``NOTION_API_KEY`` has its own assertion, and it withholds too."""
    with pytest.raises(AssertionError) as excinfo:
        _assert_settings_are_synthetic(
            _settings_carrying(NOTION_API_KEY=SENTINEL_SECRET), "probe.settings"
        )

    reported = str(excinfo.value)

    assert "NOTION_API_KEY" in reported
    assert SENTINEL_SECRET not in reported


def test_verified_settings_produce_no_failures():
    """The redaction did not turn the gate into one that never fires."""
    assert _settings_normalisation_failures(_settings_carrying()) == []


# --------------------------------------------------------------------------- #
# F25 -- a loopback port is authorized only while its socket is bound.
# --------------------------------------------------------------------------- #


def test_a_port_this_process_never_bound_is_not_owned():
    """The registry starts closed rather than open."""
    assert _is_port_owned_by_this_process(1) is False
    assert _is_port_owned_by_this_process("8080") is False


def test_a_bound_loopback_port_is_owned_and_connectable():
    """While the listener is open, a connect to it is admitted."""
    listener = socket.socket()
    try:
        listener.bind((LOOPBACK_ADDRESS, 0))
        port = listener.getsockname()[1]
        listener.listen(1)

        assert _is_port_owned_by_this_process(port) is True

        client = socket.socket()
        try:
            client.connect((LOOPBACK_ADDRESS, port))
            accepted, _ = listener.accept()
            accepted.close()
        finally:
            client.close()
    finally:
        listener.close()


def test_a_closed_loopback_port_is_no_longer_owned_or_connectable():
    """Once the listener closes, the same number is refused.

    This is the port-reuse case. The operating system may give that number to
    any process that asks for it next, so authorizing it because *this* process
    once bound it would let the suite reach whatever bound it afterwards.
    """
    listener = socket.socket()
    listener.bind((LOOPBACK_ADDRESS, 0))
    port = listener.getsockname()[1]
    listener.listen(1)
    assert _is_port_owned_by_this_process(port) is True

    listener.close()

    assert _is_port_owned_by_this_process(port) is False

    stale = socket.socket()
    try:
        with pytest.raises(UnmockedNetworkAccessError) as excinfo:
            stale.connect((LOOPBACK_ADDRESS, port))
    finally:
        stale.close()

    reported = str(excinfo.value)

    assert REFUSAL_FRAGMENT in reported
    assert str(port) in reported


def test_detaching_a_socket_also_gives_up_its_port():
    """``detach`` hands the descriptor to code this guard cannot see."""
    listener = socket.socket()
    listener.bind((LOOPBACK_ADDRESS, 0))
    port = listener.getsockname()[1]
    assert _is_port_owned_by_this_process(port) is True

    descriptor = listener.detach()
    # Re-wrapped rather than closed with ``os.close``: on Windows a socket is a
    # handle rather than a file descriptor, so only the socket API can close it.
    reclaimed = socket.socket(fileno=descriptor)
    try:
        assert _is_port_owned_by_this_process(port) is False
    finally:
        reclaimed.close()


def test_rebinding_one_socket_does_not_leave_its_first_port_owned():
    """A socket holds one claim at a time, so re-binding cannot inflate the count."""
    first = socket.socket()
    try:
        first.bind((LOOPBACK_ADDRESS, 0))
        first_port = first.getsockname()[1]
        assert _is_port_owned_by_this_process(first_port) is True
    finally:
        first.close()

    assert _is_port_owned_by_this_process(first_port) is False


def test_a_second_socket_keeps_a_shared_port_owned_until_both_close():
    """Ownership is counted, so closing one of two holders does not revoke it."""
    first = socket.socket()
    second = socket.socket()
    try:
        first.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        second.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        first.bind((LOOPBACK_ADDRESS, 0))
        port = first.getsockname()[1]
        try:
            second.bind((LOOPBACK_ADDRESS, port))
        except OSError:
            pytest.skip(
                "this platform refuses a second bind on an already-bound "
                "loopback port, so the shared-claim path is unreachable here"
            )

        assert _is_port_owned_by_this_process(port) is True

        first.close()

        assert _is_port_owned_by_this_process(port) is True
    finally:
        first.close()
        second.close()

    assert _is_port_owned_by_this_process(port) is False


# --------------------------------------------------------------------------- #
# F26 -- a child process is refused in every phase.
# --------------------------------------------------------------------------- #


def test_child_process_is_refused_during_collection():
    """The probe run at this module's scope, while pytest was collecting."""
    _assert_was_refused(COLLECTION_TIME_PROBE, "collection")
    # Outside a test the guard names the phase rather than a nodeid.
    for outcome in COLLECTION_TIME_PROBE.values():
        assert outcome.startswith(COLLECTION_SUBJECT)


@pytest.fixture(scope="module", autouse=True)
def child_process_probe_after_the_last_test():
    """Probe once more after every per-test fixture in this module has torn down.

    This is the window the guard used to leave open, and it can only be reached
    from a fixture that outlives the tests. ``block_network_access`` is autouse
    and function-scoped, so it is set up before every other function fixture and
    therefore torn down after all of them, and it clears the guard's ``test_id``
    when it goes -- which is exactly the condition the removed bypass keyed on.
    A module-scoped finalizer runs after that, with ``test_id`` back to ``None``,
    so a spawn attempted here is the one a per-test probe cannot reproduce.

    The assertion lives in the finalizer because there is no test body at
    teardown time. pytest reports a failing module-scoped finalizer as an error
    at teardown of the module's last test, so the check is enforced without any
    test depending on another test having run first.
    """
    yield
    _assert_was_refused(_probe_child_processes(), "module teardown")


@pytest.fixture
def child_process_probe_at_teardown():
    """Attempt a refused child process during one test's teardown.

    Complements :func:`child_process_probe_after_the_last_test`: this finalizer
    runs while the guard still attributes refusals to the test that requested it,
    the module-scoped one runs after that attribution is gone, and the guard has
    to refuse in both.
    """
    yield
    _assert_was_refused(_probe_child_processes(), "the teardown of one test")


def test_child_process_is_refused_during_teardown(child_process_probe_at_teardown):
    """The refusal is asserted by the fixture, after this body returns."""
    _assert_was_refused(_probe_child_processes(), "a test body")


def test_os_system_is_refused_inside_a_test():
    """The second guarded entry point, refused the same way."""
    with pytest.raises(UnmockedNetworkAccessError) as excinfo:
        os.system(UNRUNNABLE_COMMAND)

    reported = str(excinfo.value)

    assert "os.system" in reported
    assert UNRUNNABLE_COMMAND in reported


def test_a_refusal_inside_a_test_names_the_test(request):
    """Attribution still works: the subject is the running test's nodeid."""
    with pytest.raises(UnmockedNetworkAccessError) as excinfo:
        subprocess.Popen([UNRUNNABLE_COMMAND])

    assert str(excinfo.value).startswith(request.node.nodeid)


@pytest.mark.parametrize(
    "command",
    [
        "cmd /c ver",
        "cmd.exe /c ver",
        "CMD.EXE /C VER",
        r"C:\Windows\system32\cmd.exe /c ver",
        r'"C:\Windows\system32\cmd.exe" /c ver',
        "cmd.exe /c ver ",
    ],
)
def test_the_allowlist_admits_the_platform_version_probe(command):
    """The one command the standard library itself needs on Windows."""
    assert is_allowed_child_process(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "cmd.exe /c whoami",
        "cmd.exe /c ver && curl https://example.test",
        "cmd.exe /c ver | curl https://example.test",
        "cmd.exe /k ver",
        "ver",
        "curl https://example.test",
        "powershell -Command ver",
        "",
        "   ",
        None,
        ["cmd.exe", "/c", "ver"],
    ],
)
def test_the_allowlist_refuses_everything_else(command):
    """Including a widened `cmd /c`, and anything it cannot make sense of."""
    assert is_allowed_child_process(command) is False


def test_the_allowlist_is_exactly_one_pattern():
    """A second entry is a decision, so it must not arrive unnoticed."""
    assert len(ALLOWED_CHILD_PROCESS_COMMANDS) == 1


@pytest.mark.parametrize(
    ("args", "kwargs", "expected"),
    [
        (("cmd.exe /c ver",), {}, "cmd.exe /c ver"),
        ((["cmd.exe", "/c", "ver"],), {}, "cmd.exe /c ver"),
        (((b"cmd.exe", b"/c", b"ver"),), {}, "cmd.exe /c ver"),
        ((b"cmd.exe /c ver",), {}, "cmd.exe /c ver"),
        ((), {"args": ["cmd.exe", "/c", "ver"]}, "cmd.exe /c ver"),
        ((), {"cmd": "cmd.exe /c ver"}, "cmd.exe /c ver"),
        ((), {}, "<no command>"),
        ((None,), {}, "<no command>"),
        ((["cmd.exe", 7],), {}, "cmd.exe 7"),
    ],
)
def test_a_command_is_rendered_the_same_way_however_it_arrives(
    args, kwargs, expected
):
    """One normalised form, so the allow-list and the refusal message agree."""
    assert child_process_command(args, kwargs) == expected

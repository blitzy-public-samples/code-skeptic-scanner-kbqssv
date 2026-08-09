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
    see what it does. Refusal runs from :func:`tests.conftest.pytest_configure`
    -- which is before collection -- through the last teardown, rather than
    depending on whether a test happens to be executing. A shell entry point is
    refused for every command; :class:`subprocess.Popen` is refused unless
    :func:`tests.conftest.is_allowed_child_process` admits the invocation on its
    **structure**: an argument vector whose executable resolves to a trusted
    command interpreter, whose remaining members are exactly
    :data:`tests.conftest.ALLOWED_CHILD_PROCESS_ARGUMENTS`, and which asks for no
    shell.

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

@see docs/testing/DECISION-LOG.md - rows D105, D121, D223, D224, D225, D329 and
    D330.
"""

import builtins
import importlib
import logging
import multiprocessing
import os
import socket
import subprocess
import sys
import threading
import types
import typing
from types import SimpleNamespace

import pytest

import tests.conftest as suite_conftest
from tests.conftest import (
    ALLOWED_CHILD_PROCESS_ARGUMENTS,
    CHILD_PROCESS_FACTORIES,
    NATIVE_PROCESS_FACTORIES,
    REQUIRED_SETTINGS_ENV,
    SENSITIVE_SETTINGS_FIELDS,
    SESSION_TEST_ID,
    SURVIVOR_JOIN_TIMEOUT_SECONDS,
    TESTABILITY_SETTINGS_VALUES,
    UNATTRIBUTED_SUBJECT,
    UNCONDITIONAL_PROCESS_FACTORIES,
    UnmockedNetworkAccessError,
    _assert_settings_are_synthetic,
    _is_port_owned_by_this_process,
    _settings_normalisation_failures,
    child_process_argv,
    child_process_command,
    correlation_id_for,
    current_test_id,
    describe_expected_value,
    describe_unexpected_value,
    is_allowed_child_process,
    is_trusted_command_interpreter,
    native_process_command,
    process_call_detail,
    reject_surviving_threads,
    trusted_command_interpreters,
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

#: The guarded entry points probed in each phase, mapped to a call that attempts
#: one process through each. Every builder in ``conftest.py`` is represented,
#: because a regression in one would be invisible in a probe that only exercised
#: another: a construction guard on ``subprocess.Popen.__init__``, a call guard
#: judged by the allow-list on ``os.system`` and the ``spawn`` family, a native
#: guard reading two arguments on ``_winapi.CreateProcess``, and an unconditional
#: refusal on ``os.fork`` and ``multiprocessing``.
#:
#: A name this interpreter does not provide is dropped by
#: :func:`_available_entry_points`, so the POSIX-only and Windows-only entries
#: coexist here exactly as they do in ``conftest.py``.
PROBE_CALLS = {
    "subprocess.Popen": {
        "call": lambda: subprocess.Popen([UNRUNNABLE_COMMAND]),
        "target": "subprocess.Popen",
        "names_command": True,
    },
    "os.system": {
        "call": lambda: os.system(UNRUNNABLE_COMMAND),
        "target": "os.system",
        "names_command": True,
    },
    "os.popen": {
        "call": lambda: os.popen(UNRUNNABLE_COMMAND),
        "target": "os.popen",
        "names_command": True,
    },
    "os.startfile": {
        "call": lambda: os.startfile(UNRUNNABLE_COMMAND),
        "target": "os.startfile",
        "names_command": True,
    },
    "os.spawnv": {
        "call": lambda: os.spawnv(
            os.P_NOWAIT, UNRUNNABLE_COMMAND, [UNRUNNABLE_COMMAND]
        ),
        "target": "os.spawnv",
        "names_command": True,
    },
    "os.spawnl": {
        "call": lambda: os.spawnl(
            os.P_NOWAIT, UNRUNNABLE_COMMAND, UNRUNNABLE_COMMAND
        ),
        "target": "os.spawnl",
        "names_command": True,
    },
    "os.posix_spawn": {
        "call": lambda: os.posix_spawn(
            UNRUNNABLE_COMMAND, [UNRUNNABLE_COMMAND], {}
        ),
        "target": "os.posix_spawn",
        "names_command": True,
    },
    "os.execv": {
        "call": lambda: os.execv(UNRUNNABLE_COMMAND, [UNRUNNABLE_COMMAND]),
        "target": "os.execv",
        "names_command": True,
    },
    "os.fork": {
        "call": lambda: os.fork(),
        "target": "os.fork",
        # ``fork`` takes no arguments, so there is no command to report.
        "names_command": False,
    },
    "_winapi.CreateProcess": {
        "call": lambda: importlib.import_module("_winapi").CreateProcess(
            None, UNRUNNABLE_COMMAND, None, None, 0, 0, None, None, None
        ),
        "target": "_winapi.CreateProcess",
        "names_command": True,
    },
    "multiprocessing.Process.start": {
        "call": lambda: multiprocessing.Process(target=len, args=("",)).start(),
        "target": "multiprocessing.process.BaseProcess.start",
        "names_command": False,
    },
}

#: A trusted command interpreter on this platform, or ``None`` when the platform
#: names none. The positive cases below are skipped in the latter case rather
#: than asserted against a path that does not exist.
TRUSTED_INTERPRETER = next(iter(sorted(trusted_command_interpreters())), None)

#: Reason recorded when a case needs a real interpreter and there is none.
NO_INTERPRETER_REASON = (
    "this platform names no command interpreter, so there is no trusted "
    "executable for the allowed invocation"
)

#: The one invocation the guard admits, as ``Popen`` receives it.
def allowed_argv():
    """Return the argument vector :func:`is_allowed_child_process` admits."""
    return [TRUSTED_INTERPRETER, *ALLOWED_CHILD_PROCESS_ARGUMENTS]

#: Subject the guard reports for a refusal raised outside any test.
COLLECTION_SUBJECT = "collection"

#: Recorded when a probe was permitted rather than refused.
PERMITTED = "PERMITTED"

#: Prefix recorded when a probe ended in some third way -- the shape a missing
#: guard produces, since the command cannot be found.
UNEXPECTED_PREFIX = "UNEXPECTED"

#: Name every thread the survivor cases start, so an assertion can single them
#: out from whatever else the interpreter happens to be running.
SURVIVOR_THREAD_NAME = "blitzy-guard-contract-survivor"

#: Seconds a survivor probe waits.  Deliberately short: two of the three cases
#: are asserting that a thread which will *not* finish is reported, so this bounds
#: how long the suite spends proving it.
SURVIVOR_PROBE_TIMEOUT = 0.25


def _entry_point_is_available(entry_point):
    """Whether this interpreter provides the callable ``entry_point`` names.

    ``os.fork`` exists only on POSIX and ``os.startfile`` and
    ``_winapi.CreateProcess`` only on Windows, so the probe set is filtered the
    same way ``conftest.py``'s installer filters its targets - by asking the
    interpreter rather than by testing ``sys.platform``.
    """
    if entry_point in ("subprocess.Popen", "multiprocessing.Process.start"):
        return True
    module_name, _, attribute = entry_point.rpartition(".")
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return hasattr(module, attribute)


def _available_entry_points():
    """Return the probe names this interpreter can actually attempt."""
    return tuple(
        entry_point
        for entry_point in PROBE_CALLS
        if _entry_point_is_available(entry_point)
    )


def _attempt(entry_point):
    """Attempt one refused child process and report how the attempt ended.

    :param entry_point: A key of :data:`PROBE_CALLS`.
    :returns: The refusal message, :data:`PERMITTED` if the spawn was allowed
        through, or an :data:`UNEXPECTED_PREFIX` description of any other
        outcome.
    """
    try:
        PROBE_CALLS[entry_point]["call"]()
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
    """Attempt every available guarded entry point and report each outcome."""
    return {
        entry_point: _attempt(entry_point)
        for entry_point in _available_entry_points()
    }


def _assert_was_refused(outcomes, phase):
    """Assert every outcome in ``outcomes`` is a refusal naming its entry point."""
    assert sorted(outcomes) == sorted(_available_entry_points())
    for entry_point, outcome in sorted(outcomes.items()):
        probe = PROBE_CALLS[entry_point]
        assert outcome != PERMITTED, (
            "{entry_point} was permitted during {phase}; the guard must refuse "
            "every invocation tests.conftest.is_allowed_child_process does not "
            "admit, in every phase".format(entry_point=entry_point, phase=phase)
        )
        assert not outcome.startswith(UNEXPECTED_PREFIX), (
            "the {phase} probe of {entry_point} did not reach the guard at all, "
            "which means the guard was not installed: {outcome}".format(
                phase=phase, entry_point=entry_point, outcome=outcome
            )
        )
        assert REFUSAL_FRAGMENT in outcome
        assert probe["target"] in outcome
        if probe["names_command"]:
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


@pytest.mark.skipif(TRUSTED_INTERPRETER is None, reason=NO_INTERPRETER_REASON)
@pytest.mark.parametrize("delivery", ["positional", "args-keyword", "cmd-keyword"])
def test_the_guard_admits_the_platform_version_probe(delivery):
    """The one invocation the standard library itself needs on Windows."""
    argv = allowed_argv()
    if delivery == "positional":
        args, kwargs = (argv,), {}
    elif delivery == "args-keyword":
        args, kwargs = (), {"args": argv}
    else:
        args, kwargs = (), {"cmd": argv}

    assert is_allowed_child_process(args, kwargs) is True


@pytest.mark.skipif(TRUSTED_INTERPRETER is None, reason=NO_INTERPRETER_REASON)
def test_the_guard_admits_a_tuple_and_a_bytes_argument_vector():
    """Sequence kind and member encoding are not part of the judgement."""
    argv = allowed_argv()
    assert is_allowed_child_process((tuple(argv),), {}) is True
    encoded = tuple(part.encode("utf-8") for part in argv)
    assert is_allowed_child_process((encoded,), {}) is True


@pytest.mark.skipif(TRUSTED_INTERPRETER is None, reason=NO_INTERPRETER_REASON)
def test_the_guard_admits_an_unresolved_path_to_the_same_interpreter():
    """`realpath` decides, so a path with `.` and `..` segments still resolves."""
    directory, name = os.path.split(TRUSTED_INTERPRETER)
    indirect = os.path.join(directory, ".", "..", os.path.basename(directory), name)
    assert is_allowed_child_process(([indirect, *ALLOWED_CHILD_PROCESS_ARGUMENTS],), {}) is True


#: Command lines that the superseded regular-expression allow-list matched, or
#: would have matched, and that a shell would execute as more than one command.
#: Each is now refused twice over: it is a string rather than an argument vector,
#: and its executable is not a trusted interpreter.
#:
#: See ``docs/testing/DECISION-LOG.md`` row D329.
SHELL_METACHARACTER_COMMAND_LINES = [
    r"C:\safe&curl https://example.test/cmd.exe /c ver",
    r"C:\safe|powershell -c iwr https://example.test/cmd.exe /c ver",
    r"C:\safe;curl https://example.test/cmd.exe /c ver",
    r"C:\safe&&curl https://example.test/cmd.exe /c ver",
    r"C:\safe||curl https://example.test/cmd.exe /c ver",
    "C:\\safe\ncurl https://example.test\\cmd.exe /c ver",
    r"C:\safe%0Acurl https://example.test/cmd.exe /c ver",
    r"C:\safe$(curl https://example.test)/cmd.exe /c ver",
    r"C:\safe`curl https://example.test`/cmd.exe /c ver",
    r"C:\safe>out.txt/cmd.exe /c ver",
    "cmd /c ver",
    "cmd.exe /c ver",
    "CMD.EXE /C VER",
    r"C:\Windows\system32\cmd.exe /c ver",
    r'"C:\Windows\system32\cmd.exe" /c ver',
    "cmd.exe /c ver ",
]


@pytest.mark.parametrize("command_line", SHELL_METACHARACTER_COMMAND_LINES)
def test_the_guard_refuses_every_string_command_line(command_line):
    """A string is a shell command line, so no string is ever admitted."""
    assert is_allowed_child_process((command_line,), {}) is False
    assert is_allowed_child_process((), {"args": command_line}) is False


@pytest.mark.parametrize(
    "separator",
    ["&", "|", ";", "&&", "||", "\n", "\r", "%0A", "$(", "`", ">", "<", "^"],
)
def test_a_metacharacter_in_the_executable_is_refused_as_an_argument_vector(separator):
    """The path is resolved and compared, so a separator cannot hide inside it."""
    executable = "C:\\safe{0}curl\\cmd.exe".format(separator)
    argv = [executable, *ALLOWED_CHILD_PROCESS_ARGUMENTS]
    assert is_allowed_child_process((argv,), {}) is False


@pytest.mark.skipif(TRUSTED_INTERPRETER is None, reason=NO_INTERPRETER_REASON)
def test_a_metacharacter_in_an_argument_is_refused():
    """The arguments are compared exactly, so nothing can be appended to them."""
    for injected in ("ver&curl https://example.test", "ver | curl", "ver\ncurl"):
        argv = [TRUSTED_INTERPRETER, "/c", injected]
        assert is_allowed_child_process((argv,), {}) is False


def test_a_non_system_executable_named_cmd_exe_is_refused(tmp_path):
    """Trust is the resolved path, not the basename."""
    impostor = tmp_path / "cmd.exe"
    impostor.write_bytes(b"MZ")
    argv = [str(impostor), *ALLOWED_CHILD_PROCESS_ARGUMENTS]

    assert is_trusted_command_interpreter(str(impostor)) is False
    assert is_allowed_child_process((argv,), {}) is False


@pytest.mark.skipif(TRUSTED_INTERPRETER is None, reason=NO_INTERPRETER_REASON)
def test_a_shell_request_is_refused_even_with_the_allowed_argument_vector():
    """`shell=True` hands the vector to a shell, so it is never admitted."""
    argv = allowed_argv()
    assert is_allowed_child_process((argv,), {"shell": True}) is False
    assert is_allowed_child_process((argv,), {"shell": 1}) is False


@pytest.mark.skipif(TRUSTED_INTERPRETER is None, reason=NO_INTERPRETER_REASON)
def test_an_executable_override_outside_the_trusted_set_is_refused(tmp_path):
    """`executable=` replaces argv[0] at exec time, so it is judged too."""
    impostor = tmp_path / "payload.exe"
    impostor.write_bytes(b"MZ")
    argv = allowed_argv()

    assert is_allowed_child_process((argv,), {"executable": str(impostor)}) is False
    assert (
        is_allowed_child_process((argv,), {"executable": TRUSTED_INTERPRETER}) is True
    )


@pytest.mark.skipif(TRUSTED_INTERPRETER is None, reason=NO_INTERPRETER_REASON)
@pytest.mark.parametrize(
    "arguments",
    [
        ["/c", "whoami"],
        ["/k", "ver"],
        ["/c", "ver", "extra"],
        ["/c"],
        [],
        ["/C", "VER"],
        ["/c", "ver "],
        ["/c", " ver"],
    ],
)
def test_only_the_exact_argument_vector_is_admitted(arguments):
    """`ALLOWED_CHILD_PROCESS_ARGUMENTS` is compared exactly, case included."""
    argv = [TRUSTED_INTERPRETER, *arguments]
    assert is_allowed_child_process((argv,), {}) is False


@pytest.mark.parametrize(
    ("args", "kwargs"),
    [
        ((), {}),
        ((None,), {}),
        (([],), {}),
        ((["cmd.exe", "/c", 7],), {}),
        ((["cmd.exe", "/c", None],), {}),
        (({"cmd.exe", "/c", "ver"},), {}),
        ((b"cmd.exe /c ver",), {}),
        ((bytearray(b"cmd.exe /c ver"),), {}),
        ((), {"cmd": ["curl", "/c", "ver"]}),
    ],
)
def test_the_guard_refuses_what_it_cannot_make_sense_of(args, kwargs):
    """Fails closed: no argument shape falls through to a permit."""
    assert is_allowed_child_process(args, kwargs) is False


@pytest.mark.parametrize(
    ("args", "kwargs", "expected"),
    [
        ((["cmd.exe", "/c", "ver"],), {}, ["cmd.exe", "/c", "ver"]),
        (((b"cmd.exe", b"/c", b"ver"),), {}, ["cmd.exe", "/c", "ver"]),
        ((), {"args": ["cmd.exe", "/c", "ver"]}, ["cmd.exe", "/c", "ver"]),
        (("cmd.exe /c ver",), {}, None),
        ((b"cmd.exe /c ver",), {}, None),
        ((), {}, None),
        ((["cmd.exe", 7],), {}, None),
    ],
)
def test_an_argument_vector_is_recognised_only_as_a_sequence(args, kwargs, expected):
    """`None` is the answer for anything a shell would have to parse."""
    assert child_process_argv(args, kwargs) == expected


def test_every_trusted_interpreter_is_an_existing_file_with_the_expected_name():
    """The trusted set is resolved against the filesystem, not assembled by name."""
    for resolved in trusted_command_interpreters():
        assert os.path.isfile(resolved)
        assert os.path.normcase(os.path.basename(resolved)) == os.path.normcase("cmd.exe")
        assert resolved == os.path.normcase(os.path.realpath(resolved))


@pytest.mark.parametrize("candidate", ["", "   ", None, 7, b"", ["cmd.exe"]])
def test_an_unusable_interpreter_candidate_is_not_trusted(candidate):
    """Fails closed for a value that names no path at all."""
    assert is_trusted_command_interpreter(candidate) is False


def test_the_allowed_argument_vector_is_exactly_the_version_probe():
    """Widening this tuple is a decision, so it must not arrive unnoticed."""
    assert ALLOWED_CHILD_PROCESS_ARGUMENTS == ("/c", "ver")


def test_the_shell_entry_points_carry_no_allowance():
    """Every string-command entry point is refused, the allowed command included.

    None of these three can satisfy `is_allowed_child_process`, which admits only an
    argument vector, so each is refused whatever it is handed. `os.startfile` is
    Windows-only and is exercised through the probe table rather than called here.
    """
    assert CHILD_PROCESS_FACTORIES == (("os", "system"), ("os", "popen"),
                                       ("os", "startfile"))

    with pytest.raises(UnmockedNetworkAccessError):
        os.system("cmd.exe /c ver")

    with pytest.raises(UnmockedNetworkAccessError):
        os.popen("cmd.exe /c ver")


@pytest.mark.parametrize("payload", SHELL_METACHARACTER_COMMAND_LINES)
def test_the_installed_guard_refuses_a_metacharacter_payload(payload):
    """The end-to-end refusal, at both entry points, of the payload class that
    defeated the superseded command-line allow-list."""
    with pytest.raises(UnmockedNetworkAccessError):
        os.system(payload)

    with pytest.raises(UnmockedNetworkAccessError):
        subprocess.Popen(payload)

    with pytest.raises(UnmockedNetworkAccessError):
        subprocess.Popen(payload, shell=True)


def test_every_probe_names_a_declared_guard_target():
    """No probe may assert against something ``conftest.py`` does not guard.

    Otherwise a probe could pass because the *call* failed for its own reasons
    while the guard covered nothing.
    """
    declared = {
        "{0}.{1}".format(module_name, attribute)
        for module_name, attribute in (
            CHILD_PROCESS_FACTORIES
            + NATIVE_PROCESS_FACTORIES
            + UNCONDITIONAL_PROCESS_FACTORIES
        )
    }
    declared.add("subprocess.Popen")

    probed = {probe["target"] for probe in PROBE_CALLS.values()}

    assert probed <= declared, sorted(probed - declared)


@pytest.mark.parametrize(
    ("group_name", "group"),
    [
        ("CHILD_PROCESS_FACTORIES", CHILD_PROCESS_FACTORIES),
        ("NATIVE_PROCESS_FACTORIES", NATIVE_PROCESS_FACTORIES),
        ("UNCONDITIONAL_PROCESS_FACTORIES", UNCONDITIONAL_PROCESS_FACTORIES),
    ],
)
def test_each_guard_group_is_probed(group_name, group):
    """Every builder in ``conftest.py`` is exercised by at least one probe.

    The three groups are installed by three different builders - allow-list on
    the first argument, allow-list on two arguments, unconditional refusal - so a
    regression in one would be invisible to a probe set that only covered
    another. The constants carry the full surface; this asserts that each
    mechanism is represented, on whichever platform is running.
    """
    available_targets = {
        PROBE_CALLS[entry_point]["target"] for entry_point in _available_entry_points()
    }
    group_targets = {
        "{0}.{1}".format(module_name, attribute) for module_name, attribute in group
    }

    assert group_targets & available_targets, (
        "no available probe covers {group}, so its guard builder is "
        "unasserted".format(group=group_name)
    )


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


@pytest.mark.parametrize(
    ("args", "kwargs", "expected"),
    [
        # The shape `subprocess` uses on Windows: the executable is inside the
        # command line and the application name is None.
        ((None, "cmd.exe /c ver"), {}, "cmd.exe /c ver"),
        ((), {"command_line": "cmd.exe /c ver"}, "cmd.exe /c ver"),
        ((r"C:\Windows\cmd.exe", None), {}, r"C:\Windows\cmd.exe"),
        ((None, None), {}, "<no command>"),
        ((), {}, "<no command>"),
    ],
)
def test_a_native_command_is_read_from_both_of_its_positions(args, kwargs, expected):
    """``_winapi.CreateProcess`` names its command second, not first.

    Reading only the first argument would render ``<no command>`` for every call
    ``subprocess`` makes, which the allow-list would then refuse - correct by
    accident, and unable to admit the one command it exists to admit.
    """
    assert native_process_command(args, kwargs) == expected


@pytest.mark.parametrize(
    ("args", "kwargs", "expected"),
    [
        ((), {}, "<no arguments>"),
        ((1, "/bin/false", ["/bin/false"]), {}, "1 /bin/false /bin/false"),
        ((), {"env": "x"}, "env=x"),
    ],
)
def test_an_unconditional_refusal_reports_its_whole_call(args, kwargs, expected):
    """``os.spawnv`` puts a mode first, so every argument is reported.

    The allow-list never reads these, so the detail exists to name what was
    attempted rather than to be matched.
    """
    assert process_call_detail(args, kwargs) == expected


# --------------------------------------------------------------------------- #
# F27 -- a thread this run started does not outlive the guards.
# --------------------------------------------------------------------------- #


def test_a_thread_that_finishes_is_not_reported_as_a_survivor():
    """The joiner waits for a thread that is going to finish, and reports none."""
    finished = threading.Event()
    worker = threading.Thread(target=finished.set, name=SURVIVOR_THREAD_NAME)
    worker.start()

    survivors = reject_surviving_threads(timeout=SURVIVOR_PROBE_TIMEOUT)

    assert finished.is_set()
    assert [entry for entry in survivors if SURVIVOR_THREAD_NAME in entry] == []


def test_a_thread_that_will_not_finish_is_reported_and_named():
    """A thread still running when the guards come off is the reportable case.

    Released at the end, and the release is asserted, so the probe cannot itself
    become the survivor it is testing for.
    """
    release = threading.Event()
    worker = threading.Thread(
        target=release.wait, name=SURVIVOR_THREAD_NAME, daemon=True
    )
    worker.start()
    try:
        survivors = reject_surviving_threads(timeout=SURVIVOR_PROBE_TIMEOUT)

        named = [entry for entry in survivors if SURVIVOR_THREAD_NAME in entry]
        assert named, survivors
        # The report has to be actionable: the kind of thread and its identity.
        assert "daemon=True" in named[0]
        assert str(worker.ident) in named[0]
    finally:
        release.set()
        worker.join(SURVIVOR_JOIN_TIMEOUT_SECONDS)

    assert worker.is_alive() is False
    assert [
        entry
        for entry in reject_surviving_threads(timeout=SURVIVOR_PROBE_TIMEOUT)
        if SURVIVOR_THREAD_NAME in entry
    ] == []


class _NeverFinishes:
    """A stand-in for a thread that will not finish, over a simulated clock.

    ``join`` consumes the whole timeout it was handed, which is what a thread
    blocked on an event does, and advances the clock by that much - so the budget
    arithmetic is observable without the test waiting for anything. Sharing the
    real clock here would make the assertion depend on wall time under a
    coverage-traced interpreter on a loaded host, which is the flakiness the
    suite's own rules forbid.
    """

    daemon = True

    def __init__(self, clock, waits, ident):
        self._clock = clock
        self._waits = waits
        self.name = SURVIVOR_THREAD_NAME
        self.ident = ident

    def is_alive(self):
        return True

    def join(self, timeout=None):
        self._waits.append(timeout)
        self._clock.now += timeout


class _SimulatedClock:
    """The two calls :func:`reject_surviving_threads` makes on the clock."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


def test_the_joiner_shares_one_budget_across_every_survivor(monkeypatch):
    """The budget is shared, so one thread that never exits cannot stretch it.

    Three threads that never finish and a budget of one: the first consumes it and
    the rest are reported without being waited on, which is what keeps session
    teardown bounded no matter how many threads a run leaked.
    """
    clock = _SimulatedClock()
    waits = []
    stand_ins = [_NeverFinishes(clock, waits, ident) for ident in (101, 102, 103)]

    monkeypatch.setattr(suite_conftest, "time", clock)
    monkeypatch.setattr(
        suite_conftest, "_threads_started_by_this_run", lambda: stand_ins
    )

    survivors = reject_surviving_threads(timeout=SURVIVOR_PROBE_TIMEOUT)

    # One wait, of exactly the budget, not one wait per thread.
    assert waits == [SURVIVOR_PROBE_TIMEOUT]
    assert clock.now == SURVIVOR_PROBE_TIMEOUT
    # Every one of them is still reported, so nothing is lost by not waiting.
    assert len(survivors) == len(stand_ins)
    assert all(SURVIVOR_THREAD_NAME in survivor for survivor in survivors)


# --------------------------------------------------------------------------- #
# F28 -- attribution is context-local, so no record names the wrong test.
# --------------------------------------------------------------------------- #


def test_a_log_record_emitted_by_this_test_is_attributed_to_it(request):
    """The positive side: the factory stamps the running test's nodeid."""
    record = logging.getLogRecordFactory()(
        "blitzy.probe", logging.INFO, __file__, 1, "probe", (), None
    )

    assert record.test_id == request.node.nodeid
    assert record.correlation_id == correlation_id_for(request.node.nodeid)


def test_a_log_record_from_a_background_thread_is_not_attributed_to_this_test(request):
    """A thread starts with an empty context, so it reads the session subject.

    Naming this test would be worse than naming none: the record did not come
    from it, and a reader following the correlation id would land on the wrong
    subject.
    """
    attributed = []

    def emit():
        record = logging.getLogRecordFactory()(
            "blitzy.probe", logging.INFO, __file__, 1, "probe", (), None
        )
        attributed.append((record.test_id, record.correlation_id))

    worker = threading.Thread(target=emit, name=SURVIVOR_THREAD_NAME)
    worker.start()
    worker.join(SURVIVOR_JOIN_TIMEOUT_SECONDS)

    assert attributed == [(SESSION_TEST_ID, SESSION_TEST_ID)]
    assert current_test_id() == request.node.nodeid


def test_a_refusal_from_a_background_thread_is_not_attributed_to_this_test(request):
    """The same rule for the guard's own message, which CI publishes."""
    reported = []

    def attempt():
        try:
            os.system(UNRUNNABLE_COMMAND)
        except UnmockedNetworkAccessError as refusal:
            reported.append(str(refusal))

    worker = threading.Thread(target=attempt, name=SURVIVOR_THREAD_NAME)
    worker.start()
    worker.join(SURVIVOR_JOIN_TIMEOUT_SECONDS)

    assert len(reported) == 1
    assert reported[0].startswith(UNATTRIBUTED_SUBJECT)
    assert request.node.nodeid not in reported[0]


# --------------------------------------------------------------------------- #
# F29 -- the interpreter this run leaves behind is the one it entered.
# --------------------------------------------------------------------------- #


def test_the_optional_shim_is_restored_to_a_pre_existing_binding(monkeypatch):
    """A ``builtins.Optional`` this run did not introduce is handed back exactly."""
    owner = object()
    monkeypatch.setattr(suite_conftest, "_BUILTINS_PREVIOUS_OPTIONAL", owner)
    try:
        suite_conftest._restore_optional_shim()

        assert builtins.Optional is owner
    finally:
        builtins.Optional = typing.Optional


def test_the_optional_shim_is_deleted_when_this_run_introduced_it():
    """And a name this run introduced is removed rather than left bound."""
    assert suite_conftest._BUILTINS_PREVIOUS_OPTIONAL is suite_conftest._ABSENT
    try:
        suite_conftest._restore_optional_shim()

        assert hasattr(builtins, "Optional") is False
    finally:
        builtins.Optional = typing.Optional


def test_a_shimmed_binding_is_recorded_and_replayed():
    """Every module a shim was written onto goes back to what it held before.

    Driven against a synthetic module so the session's own shims are untouched:
    the registry is saved and restored around the probe, because replaying it
    mid-session would evict the stand-ins the suites still need.
    """
    module = types.ModuleType("blitzy_shim_probe")
    module.already_there = "production value"
    sys.modules[module.__name__] = module

    saved = dict(suite_conftest._SHIMMED_BINDINGS)
    suite_conftest._SHIMMED_BINDINGS.clear()
    try:
        suite_conftest._record_shimmed_binding(module, "already_there")
        suite_conftest._record_shimmed_binding(module, "introduced")
        module.already_there = "stand-in"
        module.introduced = "stand-in"

        # Recorded once: a second write must not overwrite the original value with
        # the stand-in that replaced it.
        suite_conftest._record_shimmed_binding(module, "already_there")

        suite_conftest._restore_shimmed_bindings()

        assert module.already_there == "production value"
        assert hasattr(module, "introduced") is False
        assert suite_conftest._SHIMMED_BINDINGS == {}
    finally:
        suite_conftest._SHIMMED_BINDINGS.clear()
        suite_conftest._SHIMMED_BINDINGS.update(saved)
        sys.modules.pop(module.__name__, None)


def test_the_live_shims_are_registered_for_replay(app_module):
    """The wiring: using the real fixture records the real modules.

    ``app.main``'s graph binds three names no production module defines, and every
    module that received one has to be in the registry - otherwise the sentinel
    stays on it after the run.
    """
    assert app_module.__name__ == "app.main"

    registered = set(suite_conftest._SHIMMED_BINDINGS)

    assert ("app.core.security", "verify_token") in registered
    assert ("app.services.twitter_service", "TwitterService") in registered
    assert ("app.services.llm_service", "LLMService") in registered
    # Every recorded binding is one production defines nowhere, so the replay
    # deletes rather than restores.
    for key in (
        ("app.core.security", "verify_token"),
        ("app.services.twitter_service", "TwitterService"),
        ("app.services.llm_service", "LLMService"),
    ):
        assert suite_conftest._SHIMMED_BINDINGS[key] is suite_conftest._ABSENT

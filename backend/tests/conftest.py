"""Shared test infrastructure for the Code Skeptic Scanner backend suite.

Ordering in this module is load-bearing.  Eight production modules build a
``Settings()`` at their own module scope, and pytest imports every test module
during collection, before any fixture runs.  The environment seeding, the
``Optional`` shim, the credential neutralisation and the egress guard therefore
execute at *this module's* scope.  No ``app.*`` module is imported here:
production modules are imported lazily inside a fixture through
:func:`importlib.import_module`, so the prologue has always run first.

Invariants this module enforces structurally rather than by convention:

Synthetic settings
    Every ``Settings`` field name is managed.  The eight declared without a
    default are assigned placeholders, and every defaulted one whose value a
    suite reads is assigned the string form of its declared default.  Two sets
    are removed from the environment instead: ``NOTION_API_KEY``, whose declared
    ``None`` no environment string reproduces, and the two consumer fields
    production reads although ``Settings`` declares neither.  Every assignment is
    unconditional, so no ambient value can win.

Deny-by-default egress, from before collection until after teardown
    Connect, datagram send, DNS resolution, the Windows overlapped connector and
    gRPC channel construction are refused unless the target is a socket this
    process itself owns - see :func:`_is_local_address`, and note that a loopback
    port stops being owned the moment its socket closes. Child-process creation
    is refused in every phase: the shell entry points in
    :data:`CHILD_PROCESS_FACTORIES` unconditionally, and
    :class:`subprocess.Popen` unless :func:`is_allowed_child_process` admits the
    invocation on its structure.

No credential is ever printed
    A failure that fires because a *real* credential reached a settings singleton
    reports the field and the shape of what was found, never the value - see
    :func:`describe_unexpected_value`. ``backend/tests/test_guard_contract.py``
    holds this module to all three guarantees.

Fail-closed shims
    A symbol production imports but never defines is stood in for by a value
    that *refuses*.  Each shim is installed on the defining module and on every
    already-loaded module that captured it, and reset to the sentinel on exit.
    Every such shim lives here and nowhere else, so a test can neither install
    its own nor leak one into a later test.

Nothing survives the run
    :func:`pytest_unconfigure` restores the environment, the credential patch,
    ``builtins.Optional``, the logging record factory and the socket guard.

Test correlation
    Every log record carries ``test_id`` and ``correlation_id``, which is what
    the log formats in ``backend/pytest.ini`` print.

Reasoning for every choice in this module: ``docs/testing/DECISION-LOG.md``
rows D25, D104, D105, D106, D121, D134 and D135.
``docs/testing/TRACEABILITY-MATRIX.md`` records the construct each fixture
covers.
"""

import builtins
import contextlib
import contextvars
import hashlib
import importlib
import ipaddress
import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import typing
import weakref
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

# Deterministic values shared by the whole suite.

FAKE_PROJECT = "test-project"

#: Instant used by :func:`frozen_clock`.  Epoch 1704067200; the 15-minute
#: default hardcoded in ``app/core/security.py`` puts a token's ``exp`` at
#: 1704068100.
FROZEN_INSTANT = "2024-01-01 00:00:00"

#: Values for the eight ``Settings`` fields that ``app/core/config.py``
#: declares without a default: importing ``app.core.config`` without them
#: raises a pydantic ``ValidationError``. ``Settings.Config.case_sensitive`` is
#: ``True``, so the keys are upper-case exactly as the model declares them.
#: ``NOTION_API_KEY`` is ``Optional[str] = None`` and is absent from this map.
#: Every value is an obvious placeholder; the suite uses no real credential.
#: Each is assigned unconditionally, so a value present in the surrounding
#: environment cannot reach a production module through the suite.
REQUIRED_SETTINGS_ENV = {
    "SECRET_KEY": "blitzy-test-secret-key-not-a-real-credential",
    "TWITTER_API_KEY": "test-twitter-api-key",
    "TWITTER_API_SECRET": "test-twitter-api-secret",
    "TWITTER_ACCESS_TOKEN": "test-twitter-access-token",
    "TWITTER_ACCESS_TOKEN_SECRET": "test-twitter-access-token-secret",
    "OPENAI_API_KEY": "test-openai-api-key",
    "GOOGLE_CLOUD_PROJECT": FAKE_PROJECT,
    "BIGQUERY_DATASET": "test_dataset",
}

#: ``Settings`` field names whose value must never appear in anything this suite
#: prints. Every credential the model declares is here, plus ``NOTION_API_KEY``,
#: which is ``Optional[str] = None`` and therefore holds a real key whenever the
#: surrounding environment carries one, and ``GOOGLE_CLOUD_PROJECT``, which
#: identifies the infrastructure a leaked credential reaches.
#:
#: A mismatch on one of these means an ambient variable or a ``backend/.env``
#: supplied a *real* secret in place of the synthetic one. The failure message
#: reaches stdout and ``reports/junit.xml``, so
#: :func:`describe_unexpected_value` reports the value's shape and never the
#: value.
SENSITIVE_SETTINGS_FIELDS = frozenset(
    {
        "SECRET_KEY",
        "TWITTER_API_KEY",
        "TWITTER_API_SECRET",
        "TWITTER_ACCESS_TOKEN",
        "TWITTER_ACCESS_TOKEN_SECRET",
        "TWITTER_CONSUMER_KEY",
        "TWITTER_CONSUMER_SECRET",
        "OPENAI_API_KEY",
        "NOTION_API_KEY",
        "GOOGLE_CLOUD_PROJECT",
    }
)

#: Key for the keyed digest :func:`_value_fingerprint` computes. Generated once
#: per process, so a fingerprint is comparable within one run and carries no
#: information about its input outside it. An unkeyed digest of a short secret is
#: recoverable by enumeration; a keyed one is not.
_FINGERPRINT_KEY = os.urandom(16)

#: Length of that digest. Long enough that two different values in one run do not
#: collide in practice, short enough to read in a failure message.
_FINGERPRINT_DIGEST_BYTES = 8

#: Every ``Settings`` field name that carries a declared default. The prologue
#: manages all of them, and this tuple is what puts each one in
#: :data:`MANAGED_ENVIRONMENT_NAMES` to be snapshotted and restored.
#:
#: Twelve of them are *pinned* to the string form of their declared default
#: through :data:`DEFAULTED_SETTINGS_ENV`; ``NOTION_API_KEY`` is *removed*
#: instead, through :data:`UNPINNABLE_SETTINGS_NAMES`. Either way an ambient
#: variable named after one of these cannot decide the value a suite asserts
#: against: pydantic v1 resolves a field from ``os.environ`` before falling back
#: to its default, so a shell exporting ``POPULARITY_THRESHOLD`` would otherwise
#: rewrite the popularity boundary matrix's oracle.
DEFAULTED_SETTINGS_FIELDS = (
    "PROJECT_NAME",
    "API_V1_STR",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "NOTION_API_KEY",
    "FIRESTORE_COLLECTION_TWEETS",
    "FIRESTORE_COLLECTION_USERS",
    "FIRESTORE_COLLECTION_RESPONSES",
    "DOUBT_RATING_THRESHOLD",
    "POPULARITY_THRESHOLD",
    "ALLOWED_ORIGINS",
    "ALGORITHM",
    "PROJECT_ID",
    "TWITTER_TRACK_KEYWORDS",
)

#: Names ``app/services/twitter_service.py`` and ``app/tasks/tweet_processor.py``
#: read off ``settings`` although ``Settings`` declares neither. The prologue
#: *removes* them, alongside :data:`UNPINNABLE_SETTINGS_NAMES`, so a real
#: consumer secret is not reachable from a test process. The suites covering
#: those modules supply them with ``monkeypatch``.
UNDECLARED_CONSUMER_FIELDS = ("TWITTER_CONSUMER_KEY", "TWITTER_CONSUMER_SECRET")
#: The value ``app/core/config.py`` declares for every field that carries a
#: default and whose value a suite reads from a settings singleton, rendered as
#: pydantic v1 reads it from the environment: the two ``List[str]`` fields as
#: JSON, the numeric fields as their literal digits, ``PROJECT_ID`` as the
#: empty string. Assigned unconditionally, which is what makes each singleton
#: value a fixed oracle rather than a reflection of the surrounding machine.
#: ``ALGORITHM`` is the JWT header the security suite decodes against;
#: ``POPULARITY_THRESHOLD`` is the gate the tweet-processor matrix is
#: parametrised around; ``TWITTER_TRACK_KEYWORDS`` is the ``track`` keyword the
#: stream suites assert.
DEFAULTED_SETTINGS_ENV = {
    "PROJECT_NAME": "Twitter Bot",
    "API_V1_STR": "/api/v1",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
    "FIRESTORE_COLLECTION_TWEETS": "tweets",
    "FIRESTORE_COLLECTION_USERS": "users",
    "FIRESTORE_COLLECTION_RESPONSES": "responses",
    "DOUBT_RATING_THRESHOLD": "0.7",
    "POPULARITY_THRESHOLD": "100",
    "ALLOWED_ORIGINS": "[]",
    "ALGORITHM": "HS256",
    "PROJECT_ID": "",
    "TWITTER_TRACK_KEYWORDS": "[]",
}

#: ``Settings`` fields removed from the environment rather than pinned.
#: ``NOTION_API_KEY`` is declared ``Optional[str] = None`` and an environment
#: variable can only ever supply a string, so no assignment reproduces the
#: declared value. Removing the name keeps a real key exported by the
#: surrounding machine out of the suite; the value itself is asserted by
#: ``tests/unit/test_core_config.py`` against an isolated ``Settings`` built
#: with ``_env_file=None`` instead of against a singleton.
UNPINNABLE_SETTINGS_NAMES = ("NOTION_API_KEY",)

#: Path assigned to ``GOOGLE_APPLICATION_CREDENTIALS``.  It never exists, so no
#: key file can be read even if :func:`neutralize_google_credentials` is
#: bypassed.
ABSENT_CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_blitzy_absent_credentials.json",
)

#: Every environment variable this module writes or deletes. The prologue
#: snapshots all of them and :func:`pytest_unconfigure` restores each to the
#: value it held on entry, deleting the ones that were absent, so a process that
#: imports this module — an IDE test runner inside a larger session, for
#: instance — is handed its own environment back.
MANAGED_ENVIRONMENT_NAMES = (
    tuple(REQUIRED_SETTINGS_ENV)
    + DEFAULTED_SETTINGS_FIELDS
    + UNDECLARED_CONSUMER_FIELDS
    + ("GOOGLE_APPLICATION_CREDENTIALS",)
)

#: Host names that name this machine.  A literal address is classified with
#: :mod:`ipaddress` instead; see :func:`_is_local_host`.
LOOPBACK_HOSTS = frozenset({"localhost", "ip6-localhost", ""})

#: Host names a ``bind`` may name, which is :data:`LOOPBACK_HOSTS` **without the
#: empty string**.
#:
#: For a connect, ``""`` means "this machine" and is harmless.  For a bind it
#: means *every local interface*, exactly as ``0.0.0.0`` does, so a listener on it
#: is reachable from off this host.  The distinction is the whole reason
#: :func:`_is_bindable_address` does not reuse :func:`_is_local_host`.
BINDABLE_LOOPBACK_HOSTS = frozenset({"localhost", "ip6-localhost"})

#: ``socket.AF_UNIX`` where the platform provides it, and ``None`` where it does
#: not - Windows builds of CPython 3.9 do not define it.  Read at call time by
#: :func:`_endpoint_of` and :func:`_is_local_address`, so a suite exercising the
#: ``AF_UNIX`` branch on a platform without the constant substitutes it here.
AF_UNIX_FAMILY = getattr(socket, "AF_UNIX", None)

#: Socket families whose address is a ``(host, port)`` pair.
INTERNET_FAMILIES = (socket.AF_INET, socket.AF_INET6)

#: Endpoints this process has bound and not yet released, each mapped to the
#: number of live sockets holding it.
#:
#: A key is the whole identity of an endpoint - ``(family, type, protocol,
#: address)`` - never a port number alone, and it is released when the socket
#: holding it closes.  That is what confines "a socket this run owns" to this
#: run's own sockets rather than any socket on this host.
#:
#: Written and read under :data:`_OWNED_ENDPOINTS_LOCK`.
_OWNED_ENDPOINTS = {}

#: Live weak references to the bound sockets, each mapped to the endpoint it
#: holds.  The reference's callback releases the endpoint if a socket is collected
#: without ``close`` or ``detach`` being called, which is the path
#: ``_socket.socket.__del__`` takes.
_OWNED_ENDPOINT_REFERENCES = {}

#: Serialises access to :data:`_OWNED_ENDPOINTS` and
#: :data:`_OWNED_ENDPOINT_REFERENCES`.  ``bind`` and ``close`` are reachable from
#: any thread, and starlette's ``TestClient`` runs its event loop in one.
#:
#: Re-entrant, and it has to be: :func:`_release_collected_endpoint` is a weak
#: reference callback, so the garbage collector can run it on a thread that is
#: already inside :func:`_acquire_endpoint` or :func:`_release_socket_endpoint`.
#: A non-reentrant lock deadlocks that thread, taking the whole run with it.
#: ``docs/testing/DECISION-LOG.md`` rows D224 and D330 record the requirement and
#: ``backend/tests/unit/test_egress_guard.py`` asserts both halves.
_OWNED_ENDPOINTS_LOCK = threading.RLock()

#: ``(module, attribute)`` channel factories blocked by
#: :func:`block_network_access`.  gRPC opens its sockets in the C core
#: rather than through ``socket.socket``, so channel construction is the
#: only Python-level entry point to that transport.  Targets absent from the
#: installed distribution are skipped.
GRPC_CHANNEL_FACTORIES = (
    ("grpc", "secure_channel"),
    ("grpc", "insecure_channel"),
    ("grpc.aio", "secure_channel"),
    ("grpc.aio", "insecure_channel"),
    ("google.api_core.grpc_helpers", "create_channel"),
    ("google.api_core.grpc_helpers_async", "create_channel"),
)

#: ``(module, attribute)`` name-resolution entry points blocked alongside the
#: connectors, so a hostname is refused before a DNS round trip and the UDP
#: resolver traffic a connect guard never sees is covered too.  A loopback name
#: or address resolves normally; the port check in :func:`_is_local_address` is
#: what then decides whether the connect itself is admitted.
DNS_RESOLVERS = (
    ("socket", "getaddrinfo"),
    ("socket", "gethostbyname"),
    ("socket", "gethostbyname_ex"),
    ("socket", "gethostbyaddr"),
    ("socket", "getnameinfo"),
)

#: ``(module, attribute)`` connectors that never pass through
#: ``socket.socket.connect``. ``socket.create_connection`` resolves and connects
#: in one call. A target absent from this interpreter is skipped.
OUT_OF_BAND_CONNECTORS = (("socket", "create_connection"),)

#: ``(module, "Class.method")`` connectors reached as a bound method whose second
#: argument is the address.
#:
#: A Windows proactor event loop does not connect through
#: ``socket.socket.connect``; it reaches ``ConnectEx`` on an
#: ``_overlapped.Overlapped`` instance, which is an extension type and cannot be
#: patched, so the guard sits on the last pure-Python frame above it.  This is
#: the path a literal IP address takes, which needs no resolution.
METHOD_CONNECTORS = (
    ("asyncio.windows_events", "IocpProactor.connect"),
    ("asyncio.proactor_events", "BaseProactorEventLoop.sock_connect"),
)

#: ``(module, attribute)`` process-creation entry points refused unless the
#: command they were handed is one :func:`is_allowed_child_process` admits.
#:
#: A child process is the one egress path invisible to every guard above, since
#: its sockets belong to another process.  :class:`subprocess.Popen` is guarded
#: at ``__init__`` rather than by replacing the class, so the type stays intact
#: for anything that inspects it.
#:
#: Every entry here takes the command as its **first** argument.  None of them can
#: satisfy :func:`is_allowed_child_process`, which admits only an argument *vector*,
#: so all three are refused for every command they are handed;
#: :func:`child_process_command` renders the refusal message.  ``os.popen`` is built
#: on ``Popen``, and ``subprocess.run``, ``call``, ``check_call`` and
#: ``check_output`` all construct one, so those five are already covered by the
#: ``Popen`` guard - ``os.popen`` is named anyway so that a refusal reports the entry
#: point the caller actually used.
#:
#: A target this interpreter does not provide is skipped by
#: :meth:`_EgressGuard._add`, so the Windows-only ``os.startfile`` sits here
#: harmlessly on POSIX.
#:
#: See ``docs/testing/DECISION-LOG.md`` rows D105, D223 and D311.
CHILD_PROCESS_FACTORIES = (
    ("os", "system"),
    ("os", "popen"),
    ("os", "startfile"),
)

#: ``(module, attribute)`` native process-creation calls whose command sits in
#: their second positional argument rather than their first.
#:
#: ``_winapi.CreateProcess(application_name, command_line, ...)`` puts the
#: application name first and the command line second, and ``subprocess`` passes
#: ``None`` for the first on the common path, so the generic renderer would read
#: "<no command>" and refuse the one allow-listed command.
#: :func:`native_process_command` renders these two arguments instead.
NATIVE_PROCESS_FACTORIES = (("_winapi", "CreateProcess"),)

#: ``(module, attribute)`` process-creation entry points refused
#: **unconditionally**, because no allow-list decision applies to them.
#:
#: Three reasons, one per group.  The ``spawn*`` and ``posix_spawn*`` families take
#: a mode or a path first and the command later, so the allow-list - written
#: against a rendered shell command line - has nothing to match; nothing in this
#: suite launches a named binary, and the one command
#: :func:`is_allowed_child_process` admits arrives through ``Popen`` or
#: ``os.system``, never through these.  ``os.fork`` and ``os.forkpty`` duplicate
#: this interpreter - the child inherits every socket and no guard in this module
#: can observe what it then does - and take no arguments at all.  The ``exec*``
#: family replaces this process, so it is refused too, which closes a
#: fork-then-exec pair at both ends.
#:
#: ``multiprocessing.process.BaseProcess.start`` is the one method every start
#: method (``spawn``, ``fork``, ``forkserver``) and
#: :class:`concurrent.futures.ProcessPoolExecutor` funnel through.
UNCONDITIONAL_PROCESS_FACTORIES = (
    ("os", "spawnl"),
    ("os", "spawnle"),
    ("os", "spawnlp"),
    ("os", "spawnlpe"),
    ("os", "spawnv"),
    ("os", "spawnve"),
    ("os", "spawnvp"),
    ("os", "spawnvpe"),
    ("os", "posix_spawn"),
    ("os", "posix_spawnp"),
    ("os", "fork"),
    ("os", "forkpty"),
    ("os", "execl"),
    ("os", "execle"),
    ("os", "execlp"),
    ("os", "execlpe"),
    ("os", "execv"),
    ("os", "execve"),
    ("os", "execvp"),
    ("os", "execvpe"),
    ("multiprocessing.process", "BaseProcess.start"),
)

#: Argument vector, after the executable, of the one child process this suite
#: tolerates: the Windows OS-version probe ``platform.uname()`` may run.
#:
#: See ``docs/testing/DECISION-LOG.md`` rows D105, D223 and D329.
ALLOWED_CHILD_PROCESS_ARGUMENTS = ("/c", "ver")

#: Basenames a trusted command interpreter may have, compared case-insensitively
#: through :func:`os.path.normcase`.
COMMAND_INTERPRETER_NAMES = ("cmd.exe",)

#: Environment variables naming the platform's own command interpreter, read in
#: this order by :func:`trusted_command_interpreters`.
COMMAND_INTERPRETER_ENVIRONMENT = ("COMSPEC", "ComSpec")

#: Environment variables naming the Windows installation root, under which
#: ``System32/cmd.exe`` is the interpreter's canonical location.
SYSTEM_ROOT_ENVIRONMENT = ("SystemRoot", "SYSTEMROOT", "windir")

#: Symbols production code imports but that no production module defines, each
#: mapped to the module the import reads from and to every module that binds the
#: name into its own namespace with ``from ... import ...``.
#:
#: A consumer listed here captures the *object*, so
#: :func:`_install_missing_symbol` writes to the definer and to every loaded
#: consumer, and on exit sets each loaded consumer back to the fail-closed
#: sentinel rather than restoring it.
#:
#: ``kind`` selects the sentinel shape: ``"callable"`` for a name production
#: calls, ``"class"`` for a name production instantiates or uses as an
#: annotation.
MISSING_SYMBOLS = {
    # app/api/dependencies.py line 3.
    "verify_token": {
        "definer": "app.core.security",
        "consumers": ("app.api.dependencies",),
        "kind": "callable",
    },
    # app/api/routes/tweets.py line 6.  Imported and never used.
    "TwitterService": {
        "definer": "app.services.twitter_service",
        "consumers": ("app.api.routes.tweets",),
        "kind": "class",
    },
    # app/api/routes/tweets.py line 7, app/tasks/tweet_processor.py line 4 and
    # app/tasks/response_generator.py line 3.
    "LLMService": {
        "definer": "app.services.llm_service",
        "consumers": (
            "app.api.routes.tweets",
            "app.tasks.tweet_processor",
            "app.tasks.response_generator",
        ),
        "kind": "class",
    },
    # app/tasks/response_generator.py line 1.
    "add_response": {
        "definer": "app.db.firestore",
        "consumers": ("app.tasks.response_generator",),
        "kind": "callable",
    },
}

#: Modules that bind ``get_db`` with ``from app.db.firestore import get_db``
#: and so capture the function *object* at their own import time.
#: ``app.dependency_overrides`` is keyed on that object by identity, so the
#: capture has to happen while ``get_db`` is still the real function.
GET_DB_CONSUMERS = ("app.main", "app.api.dependencies")

#: Modules that must be imported before :func:`frozen_clock` freezes the clock.
#: A first import of ``pydantic`` under a frozen clock raises ``TypeError:
#: metaclass conflict`` — it declares a class deriving from ``datetime.date``,
#: which freezegun has replaced — and leaves the package half-initialised in
#: :data:`sys.modules` for the rest of the process.
PRE_FREEZE_IMPORTS = ("pydantic", "app.core.config", "app.core.security")


#: Test a refusal is attributed to, per context.  ``None`` when no test owns the
#: context the refusal was raised in: collection, module import, teardown, or a
#: thread that did not inherit the context :func:`block_network_access` set.
#:
#: Context-local for the same reason :data:`_CURRENT_TEST_ID` is - see that
#: variable, and ``docs/testing/DECISION-LOG.md`` row D313.
_GUARD_SUBJECT = contextvars.ContextVar("blitzy_guard_subject", default=None)

#: Subject :meth:`_EgressGuard.refuse` names when :data:`_GUARD_SUBJECT` holds
#: nothing.  It begins with ``collection`` because that is the phase the case
#: covers in practice - the prologue installs the guard before collection - while
#: naming the other possibility rather than asserting the first.
UNATTRIBUTED_SUBJECT = "collection or a thread outside any test context"


class UnmockedNetworkAccessError(RuntimeError):
    """Raised when the suite reaches for a resource it does not own.

    Every refusal names the test, the operation and the target, and lists the
    boundaries a test should patch instead.
    """


class MissingProductionSymbolError(RuntimeError):
    """Raised when a shimmed symbol production never defines is actually used.

    Four names are imported by production modules and defined by none:
    ``verify_token``, ``TwitterService``, ``LLMService`` and ``add_response``.
    Each stand-in exists so its importer can load, and refuses every call.  A
    test needing a controlled result patches the attribute on the module under
    test, which is the boundary that module actually reads.

    See ``docs/testing/DECISION-LOG.md`` row D106.
    """


# --------------------------------------------------------------------------- #
# Egress guard.  Deny by default; only what cannot leave the machine passes.
# --------------------------------------------------------------------------- #


def _is_local_host(host):
    """Return ``True`` when ``host`` names this machine and nothing else.

    A literal address is parsed with :mod:`ipaddress` rather than matched as a
    string, so every canonical spelling of the loopback range is recognised -
    ``127.0.0.5``, ``::1`` and the IPv4-mapped ``::ffff:127.0.0.1`` - while
    ``10.0.0.1`` and the cloud metadata address ``169.254.169.254`` are not.
    Abbreviated shorthand such as ``127.1`` is not a valid :mod:`ipaddress`
    literal, so it is classified as remote.

    Anything that is neither a name in :data:`LOOPBACK_HOSTS` nor a parseable
    loopback or unspecified address is remote, so the classification fails
    closed.

    Naming this machine is necessary but not sufficient for a connect: see
    :func:`_is_local_address`, which requires the whole endpoint to be one a live
    socket in this process bound.  This function gates name resolution and the
    bind recorder; it never admits a connect on its own.
    """
    if host is None:
        return True
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "ignore")
    if not isinstance(host, str):
        return False
    if host in LOOPBACK_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Not a literal address, and not one of the names above: a hostname
        # this suite must not resolve.
        return False
    # ``0.0.0.0`` and ``::`` are unspecified rather than loopback; connecting to
    # either reaches this machine.
    return address.is_loopback or address.is_unspecified


def _normalized_protocol(family, socket_type):
    """Return the protocol number ``(family, socket_type)`` implies.

    ``socket.socket(AF_INET, SOCK_STREAM)`` reports ``proto == 0`` while a socket
    built from a ``getaddrinfo`` record for the same endpoint reports
    ``IPPROTO_TCP``.  Both are the same transport, so the protocol recorded in an
    endpoint key is the transport's own number rather than whichever spelling the
    caller happened to construct with.  A type outside the two transports is
    returned unchanged, so a raw socket cannot collide with a stream or datagram
    one.
    """
    if family in INTERNET_FAMILIES:
        if socket_type == socket.SOCK_STREAM:
            return socket.IPPROTO_TCP
        if socket_type == socket.SOCK_DGRAM:
            return socket.IPPROTO_UDP
    return socket_type


def _normalized_internet_address(host, port):
    """Return ``(ip_address, port)`` for an internet address, or ``None``.

    The host is parsed with :mod:`ipaddress`, so every spelling of one address
    normalises to one key while two different addresses stay distinct: a socket
    bound to ``127.0.0.1`` does not authorize ``127.0.0.2``, and an ``AF_INET6``
    bind does not authorize the ``AF_INET`` address it prints like.  ``None`` for
    anything that is not a literal address on a usable port.
    """
    if not isinstance(port, int) or port <= 0:
        return None
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "ignore")
    if not isinstance(host, str):
        return None
    try:
        return ipaddress.ip_address(host), port
    except ValueError:
        return None


def _endpoint_of(family, socket_type, address):
    """Return the endpoint key ``address`` denotes for a socket of that shape.

    ``(family, protocol, normalized_address)``, where the normalized address is
    the ``(ip_address, port)`` pair for an internet family and the filesystem
    path for ``AF_UNIX``.  ``None`` when the address is not one this guard can
    identify, which is what makes an unrecognised target refusable rather than
    admissible.

    ``socket_type`` reaches the key through :func:`_normalized_protocol`, so a
    UDP bind and a TCP connect on one number are two endpoints.
    """
    if AF_UNIX_FAMILY is not None and family == AF_UNIX_FAMILY:
        if isinstance(address, (bytes, bytearray)):
            address = bytes(address).decode("utf-8", "surrogateescape")
        if not isinstance(address, str) or address == "":
            return None
        return family, None, address
    if family not in INTERNET_FAMILIES:
        return None
    if not isinstance(address, tuple) or len(address) < 2:
        return None
    normalized = _normalized_internet_address(address[0], address[1])
    if normalized is None:
        return None
    return family, _normalized_protocol(family, socket_type), normalized


def _acquire_endpoint(sock, endpoint):
    """Record that ``sock`` holds ``endpoint`` until it is closed or collected."""
    try:
        reference = weakref.ref(sock, _release_collected_endpoint)
    except TypeError:  # pragma: no cover - every socket supports weak references
        return
    with _OWNED_ENDPOINTS_LOCK:
        _OWNED_ENDPOINT_REFERENCES[reference] = endpoint
        _OWNED_ENDPOINTS[endpoint] = _OWNED_ENDPOINTS.get(endpoint, 0) + 1


def _forget_endpoint(endpoint):
    """Drop one hold on ``endpoint``, removing it when the last one goes."""
    remaining = _OWNED_ENDPOINTS.get(endpoint)
    if remaining is None:
        return
    if remaining <= 1:
        del _OWNED_ENDPOINTS[endpoint]
    else:
        _OWNED_ENDPOINTS[endpoint] = remaining - 1


def _release_collected_endpoint(reference):
    """Weak-reference callback: release the endpoint of a collected socket."""
    with _OWNED_ENDPOINTS_LOCK:
        endpoint = _OWNED_ENDPOINT_REFERENCES.pop(reference, None)
        if endpoint is not None:
            _forget_endpoint(endpoint)


def _release_socket_endpoint(sock):
    """Release whatever endpoint ``sock`` holds.  A no-op if it holds none.

    Called from the ``close`` and ``detach`` guards, so a port stops being an
    authorization the moment the socket holding it goes away rather than at the
    end of the run.  Idempotent: ``close`` is routinely called more than once.
    """
    with _OWNED_ENDPOINTS_LOCK:
        for reference, endpoint in list(_OWNED_ENDPOINT_REFERENCES.items()):
            if reference() is sock:
                del _OWNED_ENDPOINT_REFERENCES[reference]
                _forget_endpoint(endpoint)


def _record_bound_endpoint(sock):
    """Record the endpoint ``sock`` was just bound to, if this guard owns it.

    Called after a successful ``bind``, so the address is read from
    ``getsockname()`` rather than from the requested one: a bind to port ``0`` -
    which is what :func:`socket.socketpair` and every ephemeral listener ask for -
    is only assigned its real port by the kernel.

    Only a loopback or unspecified internet address is recorded, and for
    ``AF_UNIX`` only a named path.  A bind to a routable address records nothing,
    so it authorizes nothing.
    """
    _release_socket_endpoint(sock)
    family = getattr(sock, "family", None)
    try:
        name = sock.getsockname()
    except OSError:
        return
    if AF_UNIX_FAMILY is None or family != AF_UNIX_FAMILY:
        if not isinstance(name, tuple) or len(name) < 2:
            return
        if not _is_local_host(name[0]):
            return
    endpoint = _endpoint_of(family, getattr(sock, "type", None), name)
    if endpoint is None:
        return
    _acquire_endpoint(sock, endpoint)


def _is_owned_endpoint(endpoint):
    """Return ``True`` when a live socket in this process holds ``endpoint``."""
    if endpoint is None:
        return False
    with _OWNED_ENDPOINTS_LOCK:
        # An exact match and nothing wider.  :func:`_is_bindable_address` refuses
        # a bind to an unspecified address, so no unspecified endpoint can reach
        # this registry and no rule wider than equality is justifiable here.
        return endpoint in _OWNED_ENDPOINTS


def _is_port_owned_by_this_process(port):
    """Return ``True`` when a live socket in this process holds ``port``.

    The registry is keyed on the whole endpoint identity rather than on a port
    number - see :data:`_OWNED_ENDPOINTS` for why - and admission goes through
    :func:`_is_local_address`, which matches that full key.  This is the
    port-level *projection* of the same registry, and it exists for the guard's
    own contract suite: the property under test is the port lifecycle
    (authorized while a socket holds it, de-authorized the moment that socket is
    closed, detached or collected), and a port number is the only handle the
    caller of ``bind`` has to assert it with.  Nothing in the admission path
    calls this, so the projection cannot widen what the guard admits.

    :param port: The port to ask about.  Accepts anything ``int`` accepts, so a
        caller may pass the string form; an unparseable value is not owned.
    :returns: ``True`` when some live socket of an internet family holds that
        port, on any address.
    """
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False
    with _OWNED_ENDPOINTS_LOCK:
        for family, _protocol, normalized in _OWNED_ENDPOINTS:
            if family not in INTERNET_FAMILIES:
                continue
            if normalized[1] == port:
                return True
    return False


def _is_local_address(sock, address):
    """Return ``True`` when ``address`` is a socket this process itself owns.

    One admission and nothing else: the target resolves to an endpoint key that a
    live socket in this process bound.  Naming this machine is necessary but never
    sufficient - a neighbouring checkout's dev server, an application process and
    another user's service all listen on this host, and reaching one is neither
    offline nor deterministic - and neither is being an ``AF_UNIX`` socket, since
    any process can publish one this suite must not talk to.

    ``sock`` may be ``None``, which is how :func:`socket.create_connection`
    reaches the guard: it constructs its own socket, so the family is unknown and
    the type is TCP.  The address is then matched against the owned TCP endpoints
    of both internet families and nothing else.
    """
    family = getattr(sock, "family", None)
    socket_type = getattr(sock, "type", None)
    if sock is None:
        return any(
            _is_owned_endpoint(_endpoint_of(candidate, socket.SOCK_STREAM, address))
            for candidate in INTERNET_FAMILIES
        )
    return _is_owned_endpoint(_endpoint_of(family, socket_type, address))


def _is_bindable_address(sock, address):
    """Return ``True`` when ``address`` is one this suite may bind a socket to.

    Deny by default, and narrower than :func:`_is_local_host`: an address is
    bindable only when it is an ``AF_UNIX`` path or a **loopback** address of an
    internet family.  The unspecified address of a family - ``0.0.0.0``, ``::``
    and the empty host that spells the same thing - is refused, because a socket
    bound there accepts connections on every interface this machine has. This
    host runs many clones of this repository concurrently, so such a listener is
    reachable by all of them, and by anything else that can route to the machine.

    Called by the ``bind`` guard before the real call, so a refused bind never
    reaches the operating system and never appears in the endpoint registry.

    :param sock: The socket being bound; its ``family`` decides how ``address``
        is read.
    :param address: The address the caller asked to bind.
    """
    family = getattr(sock, "family", None)
    if AF_UNIX_FAMILY is not None and family == AF_UNIX_FAMILY:
        return True
    if family not in INTERNET_FAMILIES:
        return False
    if not isinstance(address, tuple) or len(address) < 2:
        return False
    host = address[0]
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "ignore")
    if not isinstance(host, str):
        return False
    if host in BINDABLE_LOOPBACK_HOSTS:
        return True
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return False
    return parsed.is_loopback


def child_process_command(args, kwargs):
    """Render the command a child-process entry point was handed, as one string.

    The guarded entry points describe a command three different ways --
    ``os.system("...")`` takes a string, ``subprocess.Popen(["a", "b"])`` takes a
    sequence, and either may arrive as the ``args`` keyword -- so they are
    normalised here to the single form a refusal message reports.  This function
    is for the message only; :func:`is_allowed_child_process` judges the
    invocation on its structure and never on this string.

    :param args: Positional arguments the guarded callable received, with any
        bound instance already stripped.
    :param kwargs: Keyword arguments it received.
    :returns: The command line, or ``"<no command>"`` when there is none to name.
    """
    command = args[0] if args else kwargs.get("args", kwargs.get("cmd"))
    if command is None:
        return "<no command>"
    if isinstance(command, (bytes, bytearray)):
        return bytes(command).decode("utf-8", "replace")
    if isinstance(command, str):
        return command
    if isinstance(command, (list, tuple)):
        return " ".join(
            part.decode("utf-8", "replace")
            if isinstance(part, (bytes, bytearray))
            else str(part)
            for part in command
        )
    return str(command)


def process_call_detail(args, kwargs):
    """Render a whole process-creation call, whatever its signature.

    The entry points in :data:`UNCONDITIONAL_PROCESS_FACTORIES` describe what they
    would run in different positions - ``os.spawnv`` takes a mode first and
    ``os.fork`` takes nothing at all - so a refusal names *every* argument rather
    than guessing which one is the command. That keeps the message useful without
    implying the allow-list read it.

    :param args: Positional arguments the guarded callable received.
    :param kwargs: Keyword arguments it received.
    :returns: The rendered call, or ``"<no arguments>"`` for a call that had none.
    """
    rendered = [child_process_command((value,), {}) for value in args]
    rendered.extend(
        "{name}={value}".format(name=name, value=child_process_command((value,), {}))
        for name, value in sorted(kwargs.items())
    )
    if not rendered:
        return "<no arguments>"
    return " ".join(rendered)


def native_process_command(args, kwargs):
    """Render the command a native process-creation call was handed.

    ``_winapi.CreateProcess`` takes ``(application_name, command_line, ...)`` and
    ``subprocess`` passes ``None`` for the first of those whenever the executable
    is named inside the command line, so the command has to be read from both
    positions.  Both are rendered by :func:`child_process_command` and the
    non-empty results joined, which keeps one normalised form for the allow-list
    and for the refusal message.

    :param args: Positional arguments the guarded callable received.
    :param kwargs: Keyword arguments it received.
    :returns: The command line, or ``"<no command>"`` when there is none to name.
    """
    rendered = []
    for position, keyword in ((0, "application_name"), (1, "command_line")):
        if len(args) > position:
            value = args[position]
        else:
            value = kwargs.get(keyword)
        if value is None:
            continue
        part = child_process_command((value,), {})
        if part and part != "<no command>":
            rendered.append(part)
    if not rendered:
        return "<no command>"
    return " ".join(rendered)


def trusted_command_interpreters():
    """Return the normalised realpaths of the platform's own command interpreter.

    Built from :data:`COMMAND_INTERPRETER_ENVIRONMENT` and from
    ``System32/cmd.exe`` under each root in :data:`SYSTEM_ROOT_ENVIRONMENT`.  A
    candidate is admitted only when it resolves to an existing file whose
    basename is in :data:`COMMAND_INTERPRETER_NAMES`, so a symlink or a
    directory junction is judged by its target rather than by its name.

    :returns: A :class:`frozenset` of ``os.path.normcase(os.path.realpath(...))``
        strings, empty on a platform that names no interpreter.
    """
    candidates = []
    for variable in COMMAND_INTERPRETER_ENVIRONMENT:
        value = os.environ.get(variable)
        if value:
            candidates.append(value)
    for variable in SYSTEM_ROOT_ENVIRONMENT:
        value = os.environ.get(variable)
        if value:
            candidates.append(os.path.join(value, "System32", "cmd.exe"))

    trusted = set()
    for candidate in candidates:
        try:
            resolved = os.path.realpath(candidate)
            if not os.path.isfile(resolved):
                continue
        except (OSError, ValueError):
            continue
        if os.path.normcase(os.path.basename(resolved)) not in [
            os.path.normcase(name) for name in COMMAND_INTERPRETER_NAMES
        ]:
            continue
        trusted.add(os.path.normcase(resolved))
    return frozenset(trusted)


def is_trusted_command_interpreter(candidate):
    """Return ``True`` when ``candidate`` resolves to a trusted interpreter.

    :param candidate: An ``argv[0]`` or an ``executable=`` value.
    """
    if not isinstance(candidate, (str, bytes, bytearray)):
        return False
    if isinstance(candidate, (bytes, bytearray)):
        candidate = bytes(candidate).decode("utf-8", "replace")
    if candidate.strip() == "":
        return False
    try:
        resolved = os.path.realpath(candidate)
    except (OSError, ValueError):
        return False
    return os.path.normcase(resolved) in trusted_command_interpreters()


#: Depth of admitted child-process constructions on this thread.
#:
#: ``_winapi.CreateProcess`` is a command **line** API: it has no argument-vector
#: form, so :func:`is_allowed_child_process` - which judges structure and never
#: text - can never admit it directly, and parsing the string here would reopen
#: exactly the question that structural admission exists to close.  It is judged
#: by provenance instead: ``subprocess.Popen`` reaches it while constructing a call
#: this guard has already admitted, and nothing else in a test run has any reason
#: to call it.  A direct call is therefore refused, and the one admitted
#: construction still completes.
#:
#: Per-thread, because two threads may construct concurrently and one must not
#: admit the other; depth-counted, because ``Popen`` may be re-entered.
_ADMITTED_CONSTRUCTION = threading.local()


def in_admitted_construction():
    """Report whether this thread is inside an admitted child-process construction.

    :returns: ``True`` while :meth:`_EgressGuard._refuse_construction_unless_allowlisted`
        is running the real constructor for an admitted invocation.
    """
    return getattr(_ADMITTED_CONSTRUCTION, "depth", 0) > 0


def child_process_argv(args, kwargs):
    """Return the argument vector a child-process entry point was handed.

    Only a sequence is an argument vector.  A string, a bytes object or anything
    else is a command line for a platform shell to parse, which this function
    reports as ``None`` so :func:`is_allowed_child_process` refuses it.

    :param args: Positional arguments the guarded callable received, with any
        bound instance already stripped.
    :param kwargs: Keyword arguments it received.
    :returns: A list of :class:`str`, or ``None`` when there is no argument
        vector or when a member is neither text nor bytes.
    """
    command = args[0] if args else kwargs.get("args", kwargs.get("cmd"))
    if not isinstance(command, (list, tuple)):
        return None
    argv = []
    for part in command:
        if isinstance(part, (bytes, bytearray)):
            argv.append(bytes(part).decode("utf-8", "replace"))
        elif isinstance(part, str):
            argv.append(part)
        else:
            return None
    return argv


def is_allowed_child_process(args, kwargs):
    """Return ``True`` only for the one child process this suite tolerates.

    The invocation is judged on its structure, never on the text of a command
    line: it must be an argument vector whose executable resolves to a trusted
    command interpreter, whose remaining members are exactly
    :data:`ALLOWED_CHILD_PROCESS_ARGUMENTS`, and which asks for no shell.  A
    string command line, a shell request, an ``executable=`` override outside the
    trusted set and any extra argument are all refused, so no character sequence
    inside a path or an argument can widen what runs.

    Fails closed: an invocation this function cannot make sense of is refused.

    :param args: Positional arguments the guarded callable received, with any
        bound instance already stripped.
    :param kwargs: Keyword arguments it received.
    """
    if kwargs.get("shell"):
        return False

    argv = child_process_argv(args, kwargs)
    if argv is None or len(argv) != len(ALLOWED_CHILD_PROCESS_ARGUMENTS) + 1:
        return False
    if tuple(argv[1:]) != ALLOWED_CHILD_PROCESS_ARGUMENTS:
        return False
    if not is_trusted_command_interpreter(argv[0]):
        return False

    override = kwargs.get("executable")
    if override is not None and not is_trusted_command_interpreter(override):
        return False
    return True


class _EgressGuard:
    """Refuses every network operation whose target this process does not own.

    Installed by the module-scope prologue - the earliest point a conftest can
    act, and before collection imports the two production modules that build a
    Google Cloud ``Client()`` at module scope.  Released only by
    :func:`pytest_unconfigure`, so a thread that outlives the test that started
    it is still refused during teardown.

    ``test_id`` is set by :func:`block_network_access` for the duration of each
    test and reported in the error, so a refusal names the test that caused it.
    It is held in a :class:`contextvars.ContextVar`, so a refusal raised on a
    thread that did not inherit the test's context reports
    :data:`UNATTRIBUTED_SUBJECT` rather than borrowing the name of whichever test
    the main thread was running - naming the wrong test is worse than naming
    none. Outside a test the subject reads the same way, which covers collection,
    module import and teardown.

    See ``docs/testing/DECISION-LOG.md`` rows D25, D105, D121 and D313.
    """

    def __init__(self):
        self._patchers = []

    # -- attribution ------------------------------------------------------- #

    @property
    def test_id(self):
        """Nodeid attributed to a refusal raised in **this** context, or ``None``."""
        return _GUARD_SUBJECT.get()

    @test_id.setter
    def test_id(self, value):
        _GUARD_SUBJECT.set(value)

    # -- error construction ------------------------------------------------ #

    def refuse(self, operation, detail):
        """Return the :class:`UnmockedNetworkAccessError` to raise."""
        return UnmockedNetworkAccessError(
            "{subject} attempted an unmocked network call: "
            "{operation}({detail!r}). "
            "Patch the boundary the code under test uses instead, for example "
            "app.db.firestore.get_db, app.db.bigquery.Client, "
            "app.services.llm_service.Completion.create, or "
            "sys.modules['tweepy'].".format(
                subject=self.test_id or UNATTRIBUTED_SUBJECT,
                operation=operation,
                detail=detail,
            )
        )

    # -- guard factories --------------------------------------------------- #

    def _guard_socket_method(self, name, real):
        """Guard ``socket.socket.connect``/``connect_ex``: one address argument."""

        def guarded(sock, address):
            if _is_local_address(sock, address):
                return real(sock, address)
            raise self.refuse("socket." + name, address)

        return guarded

    def _guard_sendto(self, real, name="socket.sendto"):
        """Guard a datagram send whose address is its last argument.

        A UDP socket needs no ``connect``, so ``sendto`` and ``sendmsg`` are the
        datagram paths a connect guard cannot see. Both put the address last: it
        is the second argument of ``sendto`` and the fourth of ``sendmsg``, and
        both are optional on an already-connected socket, which a ``None``
        address covers.
        """

        def guarded(sock, *args):
            address = args[-1] if args else None
            if _is_local_address(sock, address):
                return real(sock, *args)
            raise self.refuse(name, address)

        return guarded

    def _guard_address_callable(self, name, real):
        """Guard a callable whose first argument is an address tuple.

        ``sock`` is ``None``: these callables construct their own socket, so
        there is no family to inspect and the address is judged on its own.
        """

        def guarded(address, *args, **kwargs):
            if _is_local_address(None, address):
                return real(address, *args, **kwargs)
            raise self.refuse(name, address)

        return guarded

    def _guard_bind(self, real):
        """Refuse a bind that would publish a listener, then record the rest.

        Two jobs.

        The refusal: a bind to a routable address, or to the unspecified address
        of a family - ``0.0.0.0`` or ``::`` - answers on interfaces this machine
        shares with everything else on the network. This host runs many clones of
        this repository at once, so a listener there is reachable by all of them
        and by anything else on the segment, which is neither offline nor
        isolated. Only a loopback address and an ``AF_UNIX`` path may be bound.

        The record: a permitted bind is what makes a later connect to that
        endpoint admissible. :func:`_is_local_address` admits a target only when a
        live socket in this process bound it, and :func:`socket.socketpair` -
        which asyncio's proactor self-pipe and starlette's ``TestClient`` portal
        both reach - binds a listener on an ephemeral loopback port before
        connecting to it.

        See ``docs/testing/DECISION-LOG.md`` row D312.
        """

        def guarded(sock, address, *args, **kwargs):
            if not _is_bindable_address(sock, address):
                raise self.refuse("socket.bind", address)
            result = real(sock, address, *args, **kwargs)
            _record_bound_endpoint(sock)
            return result

        return guarded

    def _guard_endpoint_release(self, real):
        """Release the endpoint a socket held, then run ``close``/``detach``.

        Releasing first keeps the registry from outliving the socket even if the
        underlying call raises. Nothing is refused: giving up a socket is not
        egress.
        """

        def guarded(sock, *args, **kwargs):
            _release_socket_endpoint(sock)
            return real(sock, *args, **kwargs)

        return guarded

    def _guard_method_connector(self, name, real):
        """Guard an unbound ``connect(self, sock_or_handle, address)`` method.

        The replacement is installed on the class, so it receives the instance
        as its first argument, the socket or handle as its second and the
        address as its third.
        """

        def guarded(instance, sock, address, *args, **kwargs):
            if _is_local_address(sock, address):
                return real(instance, sock, address, *args, **kwargs)
            raise self.refuse(name, address)

        return guarded

    def _guard_resolver(self, name, real):
        """Guard a name resolver whose first argument is a host or address."""

        def guarded(host, *args, **kwargs):
            target = host[0] if isinstance(host, tuple) and host else host
            if _is_local_host(target):
                return real(host, *args, **kwargs)
            raise self.refuse(name, host)

        return guarded

    def _refuse_always(self, name):
        """Return a callable that refuses regardless of its arguments."""

        def guarded(*args, **kwargs):
            detail = args[0] if args else None
            raise self.refuse(name, detail)

        return guarded

    def _refuse_unless_allowlisted(self, name, real):
        """Return a callable that refuses every command outside the allow-list.

        Used for the child-process entry points.  A child process owns its own
        sockets, so nothing else in this module can observe what it does - which
        makes it the one egress path judged by *what is being run* rather than by
        where the traffic goes.

        Unconditional in time: :func:`is_allowed_child_process` is consulted in
        every phase, so a spawn during collection, during module import or during
        teardown is refused exactly as one inside a test is.  Admission is
        structural - the one spawn the standard library itself needs is recognised
        by the shape of its argument vector, never by a command string.

        See ``docs/testing/DECISION-LOG.md`` rows D105 and D223.
        """

        def guarded(*args, **kwargs):
            if is_allowed_child_process(args, kwargs):
                return real(*args, **kwargs)
            raise self.refuse(name, child_process_command(args, kwargs))

        return guarded

    def _refuse_native_unless_allowlisted(self, name, real):
        """Return a callable that refuses a native process-creation call on its own.

        ``_winapi.CreateProcess`` takes a command *line*, so there is no argument
        vector for :func:`is_allowed_child_process` to judge and no string this guard
        will judge instead.  It is admitted only as the continuation of a construction
        already admitted on this thread - see :func:`in_admitted_construction` - which
        refuses a direct call while leaving the one admitted ``Popen`` able to finish.
        The refusal names the command line through :func:`native_process_command`.
        """

        def guarded(*args, **kwargs):
            if in_admitted_construction():
                return real(*args, **kwargs)
            raise self.refuse(name, native_process_command(args, kwargs))

        return guarded

    def _refuse_process_creation(self, name, real):
        """Return a callable that refuses a process-creation call outright.

        For the entry points in :data:`UNCONDITIONAL_PROCESS_FACTORIES`, whose
        signatures put no command where an allow-list could read one. The whole
        call is rendered by :func:`process_call_detail`, so a refusal still names
        what was attempted whatever the signature.
        """

        def guarded(*args, **kwargs):
            raise self.refuse(name, process_call_detail(args, kwargs))

        return guarded

    def _refuse_construction_unless_allowlisted(self, name, real):
        """Return an ``__init__`` replacement that refuses every child process
        outside :func:`is_allowed_child_process`.

        The instance is the :class:`subprocess.Popen` being constructed, so the
        invocation sits in the remaining positional arguments exactly as it does
        for a plain call.  The refusal is unconditional in time: the guard is
        installed by :func:`pytest_configure`, which runs before collection, and
        released only by :func:`pytest_unconfigure`, so a spawn during
        collection, module import, a test or a teardown is judged identically.

        See ``docs/testing/DECISION-LOG.md`` rows D105, D223 and D329.
        """

        def guarded(instance, *args, **kwargs):
            if is_allowed_child_process(args, kwargs):
                depth = getattr(_ADMITTED_CONSTRUCTION, "depth", 0)
                _ADMITTED_CONSTRUCTION.depth = depth + 1
                try:
                    return real(instance, *args, **kwargs)
                finally:
                    _ADMITTED_CONSTRUCTION.depth = depth
            raise self.refuse(name, child_process_command(args, kwargs))

        return guarded

    # -- lifecycle --------------------------------------------------------- #

    def _add(self, module_name, attribute, build):
        """Patch ``module.attribute`` with ``build(name, real)``.

        ``attribute`` may be dotted, in which case the leading components name
        the object holding the final attribute — ``"IocpProactor.connect"``
        patches the method on the class. A target this interpreter does not
        provide, or one whose containing object refuses attribute assignment, is
        skipped: the guard is a union of every mechanism that *can* be closed,
        and the ones that cannot are covered by another entry.
        """
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            return
        owner = module
        parts = attribute.split(".")
        for part in parts[:-1]:
            owner = getattr(owner, part, None)
            if owner is None:
                return
        final = parts[-1]
        real = getattr(owner, final, None)
        if real is None:
            return
        name = "{0}.{1}".format(module_name, attribute)
        patcher = patch.object(owner, final, build(name, real))
        try:
            patcher.start()
        except (AttributeError, TypeError):
            return
        self._patchers.append(patcher)

    def install(self):
        """Install the bind recorder and every connector, datagram, resolver and
        gRPC guard.

        The bind recorder and its release half go first, so no ephemeral loopback
        port can be bound between installing the connect guards and installing
        them.
        """
        bind_patcher = patch.object(
            socket.socket, "bind", self._guard_bind(socket.socket.bind)
        )
        bind_patcher.start()
        self._patchers.append(bind_patcher)

        # The counterparts of the recorder. Without them a released port would go
        # on authorizing connects for the rest of the run, and another process
        # could rebind it in the meantime.
        for attribute in ("close", "detach"):
            release_patcher = patch.object(
                socket.socket,
                attribute,
                self._guard_endpoint_release(getattr(socket.socket, attribute)),
            )
            release_patcher.start()
            self._patchers.append(release_patcher)

        for attribute in ("connect", "connect_ex"):
            patcher = patch.object(
                socket.socket,
                attribute,
                self._guard_socket_method(
                    attribute, getattr(socket.socket, attribute)
                ),
            )
            patcher.start()
            self._patchers.append(patcher)
        # ``sendmsg`` is absent on some platforms, so it is guarded only when the
        # interpreter exposes it.
        for attribute in ("sendto", "sendmsg"):
            real = getattr(socket.socket, attribute, None)
            if real is None:
                continue
            datagram_patcher = patch.object(
                socket.socket,
                attribute,
                self._guard_sendto(real, "socket.%s" % attribute),
            )
            datagram_patcher.start()
            self._patchers.append(datagram_patcher)

        for module_name, attribute in OUT_OF_BAND_CONNECTORS:
            self._add(module_name, attribute, self._guard_address_callable)

        for module_name, attribute in METHOD_CONNECTORS:
            self._add(module_name, attribute, self._guard_method_connector)

        for module_name, attribute in DNS_RESOLVERS:
            self._add(module_name, attribute, self._guard_resolver)

        for module_name, attribute in GRPC_CHANNEL_FACTORIES:
            self._add(
                module_name,
                attribute,
                lambda name, real: self._refuse_always(name),
            )
        # The single construction point every gRPC factory funnels into, which
        # is what defeats a reference captured before the factories were
        # patched.
        self._add(
            "grpc._channel",
            "Channel",
            lambda name, real: self._refuse_always(name),
        )

    def install_child_process_guards(self):
        """Refuse process creation at every Python-level entry point.

        Three groups, each named by its own constant:
        :data:`CHILD_PROCESS_FACTORIES` and
        :data:`NATIVE_PROCESS_FACTORIES` are judged by
        :func:`is_allowed_child_process`, and
        :data:`UNCONDITIONAL_PROCESS_FACTORIES` is refused outright.
        :class:`subprocess.Popen` is guarded at ``__init__`` below, which is what
        also closes ``subprocess.run``, ``call``, ``check_call`` and
        ``check_output``.

        Installed from :func:`pytest_configure`, which runs before collection,
        and released only by :func:`pytest_unconfigure`, so the refusal covers
        collection, every test, every teardown and session finish.

        Residual, stated because the guarantee is bounded: these are Python-level
        patches, so a process created by a C extension or through
        :mod:`ctypes` - neither of which this suite contains - would not pass
        through any of them. ``backend/tests/test_guard_contract.py`` probes every
        entry point named here.
        """
        for module_name, attribute in CHILD_PROCESS_FACTORIES:
            self._add(module_name, attribute, self._refuse_unless_allowlisted)
        for module_name, attribute in NATIVE_PROCESS_FACTORIES:
            self._add(module_name, attribute, self._refuse_native_unless_allowlisted)
        for module_name, attribute in UNCONDITIONAL_PROCESS_FACTORIES:
            self._add(module_name, attribute, self._refuse_process_creation)
        popen_patcher = patch.object(
            subprocess.Popen,
            "__init__",
            self._refuse_construction_unless_allowlisted(
                "subprocess.Popen", subprocess.Popen.__init__
            ),
        )
        popen_patcher.start()
        self._patchers.append(popen_patcher)

    def release(self):
        """Undo every patch, newest first.  Safe to call more than once."""
        while self._patchers:
            with contextlib.suppress(RuntimeError):
                self._patchers.pop().stop()


#: The single guard instance.  Installed by the prologue below.
_EGRESS_GUARD = _EgressGuard()


# --------------------------------------------------------------------------- #
# Environment bookkeeping.  Every name the prologue writes or removes is
# recorded here first, and :func:`pytest_unconfigure` replays the record.
# --------------------------------------------------------------------------- #

#: Recorded for a name the process environment did not carry.
_ABSENT = object()

#: Every ``(module name, symbol name)`` pair :func:`_install_missing_symbol` has
#: written a stand-in onto, mapped to the value that module carried *before* the
#: first write - :data:`_ABSENT` when it carried none.
#:
#: The context manager restores the defining module on exit but deliberately
#: leaves the fail-closed sentinel on every cached consumer, so that a consumer
#: which is never evicted from :data:`sys.modules` cannot be left holding a
#: permissive stand-in. That is the right state *during* a session and the wrong
#: one after it: the sentinels are test objects, and an interpreter that outlives
#: this run - an IDE runner, or a second pytest invocation in one process - would
#: keep resolving production names to them. :func:`_restore_shimmed_bindings`
#: replays this record at :func:`pytest_unconfigure`.
#:
#: See ``docs/testing/DECISION-LOG.md`` row D314.
_SHIMMED_BINDINGS = {}


def _record_shimmed_binding(module, symbol_name):
    """Record ``module``'s pre-shim binding for ``symbol_name``, once."""
    key = (module.__name__, symbol_name)
    if key not in _SHIMMED_BINDINGS:
        _SHIMMED_BINDINGS[key] = getattr(module, symbol_name, _ABSENT)


def _restore_optional_shim():
    """Return ``builtins.Optional`` to whatever this run found there.

    Two branches, and the distinction is the point: a name this run introduced is
    **deleted**, because leaving it behind would let unrelated code in this
    interpreter resolve a name Python does not define; a name that was already
    bound is set back to the **exact object** it held, because replacing someone
    else's ``Optional`` with ``typing.Optional`` is still a mutation this module
    has no right to leave behind.

    Called from :func:`pytest_unconfigure`; a separate function so both branches
    are assertable - see ``backend/tests/test_guard_contract.py``.
    """
    if _BUILTINS_PREVIOUS_OPTIONAL is _ABSENT:
        with contextlib.suppress(AttributeError):
            delattr(builtins, "Optional")
    else:
        builtins.Optional = _BUILTINS_PREVIOUS_OPTIONAL


def _restore_shimmed_bindings():
    """Return every shimmed module to the binding it had before this run.

    A module the run evicted from :data:`sys.modules` is skipped: there is nothing
    left holding the stand-in. A name that was absent before is deleted rather
    than set to ``None``, so the module is left in its real production shape.
    """
    for (module_name, symbol_name), previous in list(_SHIMMED_BINDINGS.items()):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        if previous is _ABSENT:
            with contextlib.suppress(AttributeError):
                delattr(module, symbol_name)
        else:
            setattr(module, symbol_name, previous)
    _SHIMMED_BINDINGS.clear()

#: Pre-prologue value of every environment variable the prologue changes,
#: keyed by name, holding :data:`_ABSENT` for a name that was unset.
_ENVIRONMENT_SNAPSHOT = {}


def _record_environment(name):
    """Record ``name``'s pre-prologue value, the first time it is seen."""
    if name not in _ENVIRONMENT_SNAPSHOT:
        _ENVIRONMENT_SNAPSHOT[name] = os.environ.get(name, _ABSENT)


def _restore_environment():
    """Replay :data:`_ENVIRONMENT_SNAPSHOT` onto ``os.environ``."""
    for name, previous in _ENVIRONMENT_SNAPSHOT.items():
        if previous is _ABSENT:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous
    _ENVIRONMENT_SNAPSHOT.clear()


# --------------------------------------------------------------------------- #
# Module-scope prologue.  Executed on import, before any ``app.*`` module.

# Record every managed name before the prologue changes any of them, so
# :func:`pytest_unconfigure` can hand this process its own environment back. The
# record uses the :data:`_ABSENT` sentinel rather than ``None``, which is what
# separates "was unset" from "was set to the empty string" — ``PROJECT_ID`` is
# pinned to ``""`` below, so that distinction is load-bearing here.
for _managed_name in MANAGED_ENVIRONMENT_NAMES:
    _record_environment(_managed_name)
del _managed_name

# Unconditional assignment, not setdefault: an ambient value never wins, so the
# suite is deterministic and offline whatever the surrounding machine carries.
for _setting_name, _setting_value in REQUIRED_SETTINGS_ENV.items():
    os.environ[_setting_name] = _setting_value
del _setting_name, _setting_value

# Pinned, not removed: pydantic v1 reads os.environ *before* the ``.env`` file
# named by Settings.Config.env_file, so assigning each declared default makes the
# singleton independent of a .env on disk as well as of an ambient value.
for _setting_name, _setting_value in DEFAULTED_SETTINGS_ENV.items():
    os.environ[_setting_name] = _setting_value
del _setting_name, _setting_value

# Removal, not assignment: NOTION_API_KEY is Optional[str] = None and an
# environment variable can only supply a string, so no assignment reproduces the
# declared value; the consumer fields are read off settings although Settings
# declares neither, and a real consumer secret must not be reachable from a test
# process.  The suites covering those modules supply them with monkeypatch.
for _neutralized_name in UNPINNABLE_SETTINGS_NAMES + UNDECLARED_CONSUMER_FIELDS:
    os.environ.pop(_neutralized_name, None)
del _neutralized_name

# Unconditional: neutralisation must not be defeatable by an ambient value.
_record_environment("GOOGLE_APPLICATION_CREDENTIALS")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ABSENT_CREDENTIALS_PATH

# ``app/core/security.py`` annotates ``expires_delta: Optional[timedelta]`` at
# line 11 without importing ``Optional``, so importing it raises
# ``NameError: name 'Optional' is not defined``.  ``app/api/dependencies.py``
# imports from that module and inherits the failure.
#
# The previous binding is snapshotted rather than merely tested for existence:
# an interpreter that already carried a ``builtins.Optional`` - one this suite
# did not put there, in a session that embeds this run - gets exactly that object
# back in :func:`pytest_unconfigure`, and one that carried none gets the name
# removed. Recording only "was it present" would restore presence but replace the
# value with ``typing.Optional``, which is a mutation this module has no right to
# leave behind.
_BUILTINS_PREVIOUS_OPTIONAL = getattr(builtins, "Optional", _ABSENT)
builtins.Optional = typing.Optional


def _google_credentials_class():
    """Return ``google.auth.credentials.Credentials``, imported on demand."""
    import google.auth.credentials

    return google.auth.credentials.Credentials


def _fake_credential_pair():
    """Return a ``(credential, project)`` pair that performs no I/O."""
    return MagicMock(spec=_google_credentials_class()), FAKE_PROJECT


def _fake_google_auth_default(*args, **kwargs):
    """Stand in for ``google.auth.default``; accepts any call."""
    return _fake_credential_pair()


#: ``app/db/firestore.py`` and ``app/db/bigquery.py`` construct a Google
#: Cloud ``Client()`` at module scope, which resolves credentials.  Starting
#: the patch here rather than in a fixture puts it in force before
#: collection imports either module, so ``from google.auth import default``
#: binds the stand-in.
_AMBIENT_CREDENTIAL_PATCH = patch(
    "google.auth.default", new=_fake_google_auth_default
)
_AMBIENT_CREDENTIAL_PATCH.start()

# Populate platform's two caches while no guard is installed. On Windows both of
# these obtain the OS version by running ``ver`` in a child process:
#
# * ``platform.uname()`` fills ``platform._uname_cache``, which
#   ``platform.system()`` and ``platform.node()`` also read;
# * ``platform.platform()`` fills ``platform._platform_cache``, which is a
#   *separate* cache reached through ``platform.win32_ver()``. pytest-xdist calls
#   it in every worker's ``pytest_sessionstart``, before any test runs and after
#   this conftest has installed the guard, so without this line ``pytest -n auto``
#   aborts at worker start-up with a refusal rather than running.
#
# Each call caches its result for the whole process, so the child-process guard
# below never sees a spawn the standard library itself needed.
# See ``docs/testing/DECISION-LOG.md`` rows D105 and D315.
platform.uname()
platform.platform()

# Last step of the prologue: deny egress from here until pytest_unconfigure.
_EGRESS_GUARD.install()


def _spawns_worker_processes(config):
    """Return ``True`` when this process is a pytest-xdist controller.

    A controller runs no test of its own; it spawns each worker with
    :class:`subprocess.Popen` through execnet, so the child-process guard would
    stop the run before a single test executed. A worker — identified by the
    ``workerinput`` attribute xdist attaches to its config — does run tests and
    is guarded.
    """
    if hasattr(config, "workerinput"):
        return False
    if getattr(config.option, "numprocesses", None):
        return True
    return getattr(config.option, "dist", "no") not in (None, "no")


#: Values the four fields ``app/core/config.py`` declares for testability must
#: carry on the singleton. Each name is assigned the string form of its declared
#: default by the prologue, through :data:`DEFAULTED_SETTINGS_ENV`, so no ambient
#: value and no ``.env`` entry can decide it; these are the parsed results of
#: those assignments and equal the defaults at ``app/core/config.py`` lines 22-25.
TESTABILITY_SETTINGS_VALUES = {
    "ALLOWED_ORIGINS": [],
    "ALGORITHM": "HS256",
    "PROJECT_ID": "",
    "TWITTER_TRACK_KEYWORDS": [],
}

#: Environment names that must be *absent* once the prologue has run, because no
#: environment string reproduces the declared value (``NOTION_API_KEY``) or
#: because ``Settings`` declares no such field at all (the consumer fields).
DEFAULTED_SETTINGS_ENV_NAMES = UNPINNABLE_SETTINGS_NAMES + UNDECLARED_CONSUMER_FIELDS


def describe_unexpected_value(field_name, actual):
    """Return a non-disclosing description of ``actual`` for a failure message.

    Every field this module checks is either a credential or a threshold the
    suite pins, and the credential fields are exactly the ones whose real values
    must never be printed: a failure here means an ambient variable or a
    ``backend/.env`` supplied a *real* secret, and both pytest's own output and
    ``reports/junit.xml`` are read, archived and pasted into tickets. A message
    carrying the value would publish the secret it exists to warn about.

    A field named in :data:`SENSITIVE_SETTINGS_FIELDS` is therefore described by
    its shape alone -- type, character length, and the short digest
    :func:`_value_fingerprint` computes -- which is enough to tell two wrong
    values apart and to recognise the same wrong value twice, and not enough to
    reconstruct either. Any other field is shown, because a threshold or a
    collection name is diagnostic rather than secret and seeing it is what makes
    the failure actionable.

    :param field_name: ``Settings`` field the value was read from.
    :param actual: Value found on the settings object.
    :returns: A description safe to print in any context the suite writes to.
    """
    if field_name not in SENSITIVE_SETTINGS_FIELDS:
        return repr(actual)
    if actual is None:
        return "absent (None)"
    rendered = actual if isinstance(actual, str) else repr(actual)
    return "a {kind} of {length} characters, fingerprint {digest} " "(value withheld)".format(
        kind=type(actual).__name__,
        length=len(rendered),
        digest=_value_fingerprint(rendered),
    )


def describe_expected_value(field_name):
    """Return how a failure message should name the value the suite assigns.

    The expected values are committed constants in this module rather than
    secrets, so naming one discloses nothing. A credential field is still
    described by reference rather than by value, so that no message written by
    this suite pairs a credential field name with a credential-shaped literal --
    which is what makes an operator reading a failure able to tell at a glance
    that nothing sensitive is in it.

    :param field_name: ``Settings`` field being reported.
    :returns: The expected value, or a pointer to where it is declared.
    """
    if field_name in SENSITIVE_SETTINGS_FIELDS:
        return "the synthetic placeholder declared for it in backend/tests/conftest.py"
    expected_values = dict(REQUIRED_SETTINGS_ENV)
    expected_values.update(TESTABILITY_SETTINGS_VALUES)
    return repr(expected_values[field_name])


def _value_fingerprint(rendered):
    """Return a short keyed digest of ``rendered``, for telling values apart.

    Keyed with :data:`_FINGERPRINT_KEY`, a value generated once per process, so
    the digest is stable for the length of a run -- two messages naming the same
    fingerprint refer to the same value -- and carries no information about the
    input outside it. An unkeyed digest of a short, low-entropy secret is
    recoverable by enumeration, which is the whole reason this is keyed.
    """
    digest = hashlib.blake2s(
        rendered.encode("utf-8", "replace"),
        key=_FINGERPRINT_KEY,
        digest_size=_FINGERPRINT_DIGEST_BYTES,
    )
    return digest.hexdigest()


def _settings_normalisation_failures(settings):
    """Return a message per field whose value is not the one assigned above.

    ``settings`` is the singleton ``app/core/config.py`` line 32 builds, which
    is the object production modules read. Each expected value comes from
    :data:`REQUIRED_SETTINGS_ENV` or :data:`TESTABILITY_SETTINGS_VALUES`, and
    every name in :data:`DEFAULTED_SETTINGS_ENV_NAMES` is additionally required
    to be absent from the environment so its declared default governs.

    A mismatched credential field is reported through
    :func:`describe_unexpected_value`, so the message names the field and the
    shape of what was found without disclosing it.
    """
    failures = []
    expected_values = dict(REQUIRED_SETTINGS_ENV)
    expected_values.update(TESTABILITY_SETTINGS_VALUES)
    for field_name, expected in expected_values.items():
        actual = getattr(settings, field_name, None)
        if actual != expected:
            failures.append(
                "settings.{field} is {actual}; the suite assigns {expected}".format(
                    field=field_name,
                    actual=describe_unexpected_value(field_name, actual),
                    expected=describe_expected_value(field_name),
                )
            )
    for field_name in DEFAULTED_SETTINGS_ENV_NAMES:
        if field_name in os.environ:
            failures.append(
                "{field} is set in the environment; it must be unset so the "
                "default declared in app/core/config.py governs".format(
                    field=field_name
                )
            )
    return failures


#: Seconds :func:`reject_surviving_threads` spends, in total, waiting for the
#: threads a run started to finish.  Long enough for an event-loop thread or a
#: blocking portal to unwind, short enough that a thread which never exits is
#: reported rather than waited on.
SURVIVOR_JOIN_TIMEOUT_SECONDS = 5.0

#: Threads alive when this module was imported, by identity.  Everything else
#: alive at session finish was started by this run.
_BASELINE_THREAD_IDS = frozenset(
    thread.ident for thread in threading.enumerate() if thread.ident is not None
)


def _describe_thread(thread):
    """Return one line naming a thread, its kind and where it came from."""
    return "{name} (ident={ident}, daemon={daemon}, target={target})".format(
        name=thread.name,
        ident=thread.ident,
        daemon=thread.daemon,
        target=getattr(thread, "_target", None),
    )


def _threads_started_by_this_run():
    """Return every live thread this run started, excluding the caller's own."""
    current = threading.current_thread()
    return [
        thread
        for thread in threading.enumerate()
        if thread is not current
        and thread.ident not in _BASELINE_THREAD_IDS
        and thread.is_alive()
    ]


def reject_surviving_threads(timeout=SURVIVOR_JOIN_TIMEOUT_SECONDS):
    """Join every thread this run started and report the ones still alive.

    The guards in this module are process-wide monkey patches, so releasing them
    while a thread a test started is still running hands that thread an
    unguarded interpreter: it can wait for the release and then connect or spawn,
    with nothing left to refuse it and no test left to attribute it to. Joining
    first closes that window, and a thread that will not join is reported so the
    run fails rather than ending quietly with work still in flight.

    Called from :func:`pytest_sessionfinish`, which can fail the session, and
    again from :func:`pytest_unconfigure` immediately before the release.

    :param timeout: Total seconds to spend joining, shared across all survivors,
        so one thread that never exits cannot stretch the wait per thread.
    :returns: A description of every thread still alive afterwards, empty when
        all of them finished.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    for thread in _threads_started_by_this_run():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        with contextlib.suppress(RuntimeError):
            thread.join(remaining)
    return [_describe_thread(thread) for thread in _threads_started_by_this_run()]


def pytest_sessionfinish(session, exitstatus):
    """Fail the session when a thread it started is still running.

    Runs after the last test and before :func:`pytest_unconfigure`, which is the
    only point at which the outcome can still be changed: the guards are released
    in that later hook, so a survivor detected here is one that would otherwise
    outlive them.

    Skipped on a pytest-xdist controller for the same reason the child-process
    guard is: a controller runs no test of its own and keeps a communication
    thread per worker, so every thread alive here is one it started on purpose.
    Each worker runs this hook over its own tests.
    """
    if _spawns_worker_processes(session.config):
        return

    survivors = reject_surviving_threads()
    if not survivors:
        return

    report = [
        "{count} thread(s) started by this run are still alive after the last "
        "test. The egress guards are released moments from now, so a thread that "
        "is still running would then be free to connect or to spawn with nothing "
        "left to refuse it. Join or stop every thread a test starts:".format(
            count=len(survivors)
        )
    ]
    report.extend("  - " + survivor for survivor in survivors)
    message = "\n".join(report)

    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:  # pragma: no cover - the plugin is always registered
        print(message)
    else:
        reporter.write_sep("=", "surviving threads", red=True)
        reporter.write_line(message)

    if session.exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_configure(config):
    """Add the child-process guard, then refuse the run unless settings verify.

    Two jobs, in this order, because both need the parsed configuration and both
    must complete before collection imports any ``app.*`` module.

    The child-process guard is the one egress guard the prologue cannot install
    on its own: it has to be skipped on a pytest-xdist controller, which spawns
    its workers legitimately, and only the parsed configuration says whether
    this process is one. Every other guard is already in force.

    The readiness gate then verifies the normalisation. The prologue assigns
    every environment input ``Settings`` reads, but a ``.env`` file, a plugin or
    a sitecustomize hook could still supply one, and the consequence would be
    silent: ``app/db/firestore.py`` line 10 passes ``settings.PROJECT_ID`` to
    ``Client(project=...)``, and every credential field reaches a third-party
    client.

    Importing ``app.core.config`` here is the first ``app.*`` import of the run,
    which happens after the prologue and after ``pytest-cov`` has started
    measuring in ``pytest_load_initial_conftests``.

    Raises :class:`pytest.UsageError` naming every field that disagrees, and
    likewise when the import itself fails — for example when a ``.env`` file
    exists in the working directory and ``python-dotenv``, which pydantic v1
    needs to read one, is not installed.
    """
    if not _spawns_worker_processes(config):
        _EGRESS_GUARD.install_child_process_guards()

    try:
        settings = importlib.import_module("app.core.config").settings
    except Exception as failure:
        raise pytest.UsageError(
            "backend/tests/conftest.py could not import app.core.config, so "
            "the backend settings cannot be verified: "
            "{name}: {failure}".format(
                name=type(failure).__name__, failure=failure
            )
        )
    failures = _settings_normalisation_failures(settings)
    if failures:
        raise pytest.UsageError(
            "backend/tests/conftest.py could not normalise the backend "
            "settings; refusing to run against unverified configuration:"
            "\n  - " + "\n  - ".join(failures)
        )


def pytest_unconfigure(config):
    """Undo every global mutation this module made, in reverse order.

    Runs after the last fixture teardown, so the egress guard is still in force
    while a session-scoped fixture unwinds and while a thread started by a test
    is still alive.

    Invariant: the interpreter this run leaves behind is the one it entered - no
    seeded variable, no credential patch, no injected builtin, no shimmed
    production name, no replaced logging factory and no socket guard survives.
    """
    # Before the release, not after: a thread still running when the patches come
    # off has an unguarded interpreter. :func:`pytest_sessionfinish` has already
    # failed the session if any of them refused to finish; this call is what
    # actually waits for them. Skipped on an xdist controller, whose live threads
    # are the worker channels it owns.
    if not _spawns_worker_processes(config):
        reject_surviving_threads()

    _EGRESS_GUARD.release()

    # The recorder is gone, so nothing can add to the registry; emptying it means
    # a second pytest invocation in this interpreter starts with no endpoint
    # authorized rather than inheriting this run's.
    with _OWNED_ENDPOINTS_LOCK:
        _OWNED_ENDPOINTS.clear()
        _OWNED_ENDPOINT_REFERENCES.clear()

    # Installed at this module's scope; a run inside a larger session - an IDE
    # test runner, or a second pytest invocation in one interpreter - would
    # otherwise keep stamping `test_id` and `correlation_id` onto every record
    # any code in the process emits.
    logging.setLogRecordFactory(_BASE_LOG_RECORD_FACTORY)

    with contextlib.suppress(RuntimeError):
        _AMBIENT_CREDENTIAL_PATCH.stop()
    _restore_environment()

    # Every module a shim was written onto goes back to the binding it had before
    # this run, which for all five of them is no binding at all: production
    # defines none of these names.
    _restore_shimmed_bindings()

    _restore_optional_shim()


# --------------------------------------------------------------------------- #
# Test correlation.  Every log record carries the test that produced it.
# --------------------------------------------------------------------------- #

#: ``test_id`` and ``correlation_id`` reported for a record emitted outside a
#: test, for example during collection or at session teardown.
SESSION_TEST_ID = "session"

#: Bytes of the correlation digest.  Eight hex characters, which is short enough
#: to prefix every live log line and wide enough that two of this suite's tests
#: will not collide.
_CORRELATION_DIGEST_BYTES = 4

#: Record factory installed below wraps this one.
_BASE_LOG_RECORD_FACTORY = logging.getLogRecordFactory()

#: Test currently executing, as its pytest nodeid.  Maintained by
#: :func:`pytest_runtest_logstart` and :func:`pytest_runtest_logfinish`.
#:
#: A :class:`contextvars.ContextVar` rather than a plain global, and the
#: difference is an attribution guarantee. A thread starts with an empty context,
#: so a record emitted from a background thread - one a test started and did not
#: join, or the event-loop thread starlette's ``TestClient`` runs - reads
#: :data:`SESSION_TEST_ID` here instead of the nodeid of whichever test happened
#: to be executing on the main thread. Naming a test that did not emit the record
#: is worse than naming none: it sends a reader to the wrong subject, and in a
#: refusal message it attributes an egress attempt to the wrong test. An
#: :class:`asyncio` task copies the current context, so an ``async`` test's own
#: awaits keep their attribution.
#:
#: See ``docs/testing/DECISION-LOG.md`` row D313.
_CURRENT_TEST_ID = contextvars.ContextVar(
    "blitzy_current_test_id", default=SESSION_TEST_ID
)


def current_test_id():
    """Return the nodeid of the test running in **this** context.

    :data:`SESSION_TEST_ID` outside a test, and also inside a thread that did not
    inherit the context the test set - see :data:`_CURRENT_TEST_ID`.
    """
    return _CURRENT_TEST_ID.get()


def correlation_id_for(test_id):
    """Return the short stable correlation id of ``test_id``.

    A digest of the pytest nodeid, so the same test yields the same id on every
    run and on every machine, and two runs of one test are comparable line by
    line. :data:`SESSION_TEST_ID` maps to itself.
    """
    if test_id == SESSION_TEST_ID:
        return SESSION_TEST_ID
    digest = hashlib.blake2s(
        test_id.encode("utf-8"), digest_size=_CORRELATION_DIGEST_BYTES
    )
    return digest.hexdigest()


def _log_record_factory(*args, **kwargs):
    """Add ``test_id`` and ``correlation_id`` to every :class:`logging.LogRecord`.

    ``log_cli_format`` and ``log_format`` in ``backend/pytest.ini`` reference
    ``correlation_id``, so the attribute has to be present on records from
    production code, from pytest and from any library, which a factory
    guarantees and a per-logger filter would not.
    """
    record = _BASE_LOG_RECORD_FACTORY(*args, **kwargs)
    test_id = current_test_id()
    record.test_id = test_id
    record.correlation_id = correlation_id_for(test_id)
    return record


logging.setLogRecordFactory(_log_record_factory)


def pytest_runtest_logstart(nodeid, location):
    """Attribute subsequent log records to the test that is starting.

    Set on the context of the thread pytest runs the test on, which is the thread
    the test body and its fixtures execute in.
    """
    _CURRENT_TEST_ID.set(nodeid)


def pytest_runtest_logfinish(nodeid, location):
    """Return attribution to the session once a test has finished."""
    _CURRENT_TEST_ID.set(SESSION_TEST_ID)


# Shim installation.


def _missing_symbol_message(symbol_name):
    """Return the text every fail-closed sentinel raises with."""
    spec = MISSING_SYMBOLS[symbol_name]
    return (
        "{symbol} is imported from {definer} by {consumers} and is defined by "
        "no production module. backend/tests/conftest.py stands it up only so "
        "the import resolves, and the stand-in refuses every use so no code "
        "path can succeed against it. Patch the attribute on the module under "
        "test to give this call a controlled result.".format(
            symbol=symbol_name,
            definer=spec["definer"],
            consumers=", ".join(spec["consumers"]),
        )
    )


def _fail_closed_callable(symbol_name):
    """Return a callable that refuses every call with a named error."""
    message = _missing_symbol_message(symbol_name)

    def refuse(*args, **kwargs):
        raise MissingProductionSymbolError(message)

    refuse.__name__ = "refuse_{0}".format(symbol_name)
    refuse.__qualname__ = refuse.__name__
    refuse.__doc__ = message
    return refuse


def _fail_closed_class(symbol_name):
    """Return a class that refuses construction with a named error.

    A class rather than a function because production both instantiates these
    names — ``app/api/routes/tweets.py`` line 31,
    ``app/tasks/tweet_processor.py`` line 14 — and uses one as a class-body
    annotation at ``app/tasks/tweet_processor.py`` line 10, which is evaluated
    when the class is created.
    """
    message = _missing_symbol_message(symbol_name)

    def __init__(self, *args, **kwargs):
        raise MissingProductionSymbolError(message)

    return type(
        "FailClosed{0}".format(symbol_name),
        (object,),
        {"__init__": __init__, "__doc__": message},
    )


def _fail_closed_sentinel(symbol_name):
    """Return the fail-closed stand-in for ``symbol_name``."""
    if MISSING_SYMBOLS[symbol_name]["kind"] == "class":
        return _fail_closed_class(symbol_name)
    return _fail_closed_callable(symbol_name)


def _loaded_consumers(symbol_name):
    """Return the already-imported modules that captured ``symbol_name``."""
    return [
        module
        for module in (
            sys.modules.get(consumer)
            for consumer in MISSING_SYMBOLS[symbol_name]["consumers"]
        )
        if module is not None
    ]


@contextlib.contextmanager
def _install_missing_symbol(symbol_name, replacement=None):
    """Bind ``symbol_name`` across its definer and every loaded consumer.

    ``replacement`` defaults to the fail-closed sentinel, which is what every
    caller should use unless a documented current-behaviour assertion needs a
    permissive value — ``tweet_processor_module`` and
    ``response_generator_module`` are the only two that do, and each explains
    why.

    On exit the definer's previous binding is restored, or the attribute deleted
    when it had none, which returns that module to its real production shape.
    Every consumer that is loaded *at exit* — including one imported inside the
    block — is set to the fail-closed sentinel rather than restored, because a
    consumer only ever holds this name as a result of a shim: production defines
    it nowhere, and ``app.main``, ``app.api.dependencies`` and
    ``app.api.routes.tweets`` are deliberately never evicted, so anything
    permissive left on them would still be there for the next test.

    Yields the installed value.
    """
    spec = MISSING_SYMBOLS[symbol_name]
    definer = importlib.import_module(spec["definer"])
    sentinel = _fail_closed_sentinel(symbol_name)
    value = sentinel if replacement is None else replacement

    had_attribute = hasattr(definer, symbol_name)
    previous = getattr(definer, symbol_name, None)
    _record_shimmed_binding(definer, symbol_name)
    setattr(definer, symbol_name, value)
    for consumer in _loaded_consumers(symbol_name):
        _record_shimmed_binding(consumer, symbol_name)
        setattr(consumer, symbol_name, value)
    try:
        yield value
    finally:
        if had_attribute:
            setattr(definer, symbol_name, previous)
        else:
            delattr(definer, symbol_name)
        for consumer in _loaded_consumers(symbol_name):
            _record_shimmed_binding(consumer, symbol_name)
            setattr(consumer, symbol_name, sentinel)


# Helpers used by the fixtures below.


@contextlib.contextmanager
def _application_shims():
    """Install the three fail-closed shims ``app.main``'s import graph needs.

    Each stands in for a symbol production code imports but that no production
    module defines: ``verify_token`` on ``app.core.security``
    (``app/api/dependencies.py`` line 3), ``TwitterService`` on
    ``app.services.twitter_service`` (``app/api/routes/tweets.py`` line 6) and
    ``LLMService`` on ``app.services.llm_service``
    (``app/api/routes/tweets.py`` line 7 and ``app/tasks/tweet_processor.py``
    line 4, which ``app/main.py`` line 5 pulls in).

    All three refuse rather than succeed: each raises
    :class:`MissingProductionSymbolError` on call or construction. Nothing in the
    import graph uses any of them at import time — ``TwitterService`` is imported
    and never referenced again, and both ``LLMService()`` calls sit inside function
    bodies — so the application still assembles, while a request that reaches one
    fails loudly. In particular no token authorizes anything:
    ``app/api/dependencies.py`` line 13 returns whatever ``verify_token``
    produced, and this stand-in produces nothing.

    A test that needs a controlled result patches the attribute on the module
    under test; ``backend/tests/unit/test_api_dependencies.py`` shows the idiom.

    See ``docs/testing/DECISION-LOG.md`` row D106.
    """
    with _install_missing_symbol("verify_token"), _install_missing_symbol(
        "TwitterService"
    ), _install_missing_symbol("LLMService"):
        yield


def _import_get_db_consumers():
    """Import every module in :data:`GET_DB_CONSUMERS` exactly once, early.

    Called before any fixture replaces ``app.db.firestore.get_db``, so the
    ``Depends(get_db)`` defaults on the tweets router hold the real function
    and ``app.dependency_overrides[get_db]`` matches them by identity.
    """
    if all(name in sys.modules for name in GET_DB_CONSUMERS):
        return
    with _application_shims():
        for name in GET_DB_CONSUMERS:
            importlib.import_module(name)


# --------------------------------------------------------------------------- #
# Autouse fixtures.


def _assert_settings_are_synthetic(settings, description):
    """Assert every required field on ``settings`` holds its test value.

    The failure this raises is the one that fires when a *real* credential has
    reached a settings singleton, so it is reported through
    :func:`describe_unexpected_value` rather than by interpolating the value: an
    assertion message travels into stdout and into ``reports/junit.xml``, and a
    message carrying the secret would disclose exactly what it exists to warn
    about.

    Each check raises :class:`AssertionError` explicitly instead of using an
    ``assert`` statement, and that is not a style choice. pytest rewrites the
    assertions in this module and appends its own explanation, which renders the
    ``repr`` of both operands -- so a bare ``assert actual == expected`` would
    print the leaked credential, and the settings object holding it, underneath a
    message written specifically to withhold them. Raising leaves nothing for the
    rewriter to introspect.
    """
    for field_name, expected in REQUIRED_SETTINGS_ENV.items():
        actual = getattr(settings, field_name)
        if actual != expected:
            raise AssertionError(
                "{description}.{field} is {actual}; the suite requires "
                "{expected}. An ambient environment variable or a backend/.env "
                "file is supplying a real one.".format(
                    description=description,
                    field=field_name,
                    actual=describe_unexpected_value(field_name, actual),
                    expected=describe_expected_value(field_name),
                )
            )
    if settings.NOTION_API_KEY is not None:
        raise AssertionError(
            "{description}.NOTION_API_KEY is {actual}; it must be None. "
            "NOTION_API_KEY is set in the environment or in backend/.env.".format(
                description=description,
                actual=describe_unexpected_value(
                    "NOTION_API_KEY", settings.NOTION_API_KEY
                ),
            )
        )


@pytest.fixture(scope="session", autouse=True)
def verify_settings_singletons():
    """Assert the settings the suite runs against are the synthetic ones.

    The prologue forces the environment before any ``app`` module is imported,
    and this fixture checks the result on the objects production code actually
    reads: ``app.core.config.settings`` plus the independent ``Settings()`` that
    ``app/main.py``, ``app/core/security.py``, the three services and the two
    tasks each build at their own module scope. Anything the environment could
    not reach — a ``backend/.env`` on disk, for instance, which
    ``Settings.Config.env_file`` names — is caught here rather than surfacing as
    an unexplained assertion failure somewhere downstream.

    Importing ``app.core.config`` here also loads ``pydantic`` before any test
    freezes the clock, which is the ordering :data:`PRE_FREEZE_IMPORTS`
    documents.

    Yields the ``app.core.config`` module.
    """
    config = importlib.import_module("app.core.config")
    _assert_settings_are_synthetic(config.settings, "app.core.config.settings")

    for module_name, module in sorted(sys.modules.items()):
        if module is None or not module_name.startswith("app."):
            continue
        candidate = getattr(module, "settings", None)
        if isinstance(candidate, config.Settings):
            _assert_settings_are_synthetic(
                candidate, "{0}.settings".format(module_name)
            )

    yield config


@pytest.fixture(autouse=True)
def neutralize_google_credentials():
    """Make Google credential resolution deterministic and offline.

    ``google.auth.default`` is replaced with a stand-in returning a
    ``MagicMock`` credential and :data:`FAKE_PROJECT`.  ``app.db.firestore``
    binds that name into its own namespace, so it is patched there too when
    the module is loaded.

    The stand-in returns rather than raises, so a code path that reaches a
    real client surfaces as an :class:`UnmockedNetworkAccessError` and not
    as a credential error.

    Yields the ``(credential, project)`` pair.
    """
    fake_pair = _fake_credential_pair()
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch("google.auth.default", return_value=fake_pair)
        )
        firestore = sys.modules.get("app.db.firestore")
        if firestore is not None and hasattr(firestore, "default"):
            stack.enter_context(
                patch.object(firestore, "default", return_value=fake_pair)
            )
        yield fake_pair


@pytest.fixture(autouse=True)
def block_network_access(request):
    """Name the running test in every egress refusal.

    The guard itself is :data:`_EGRESS_GUARD`, installed by this module's
    prologue and released only by :func:`pytest_unconfigure`. It is deliberately
    *not* installed here: a fixture runs after collection, and collection imports
    ``app/db/firestore.py`` and ``app/db/bigquery.py``, each of which constructs
    a Google Cloud ``Client()`` at module scope. A fixture-scoped guard also
    leaves teardown and any thread outliving a test unprotected.

    What this fixture contributes is attribution — the guard reports
    ``request.node.nodeid`` instead of ``collection`` while the test runs — and
    nothing else. Nothing is installed or removed, so no window exists in which
    egress is permitted.

    Refused: ``socket.socket.connect``/``connect_ex``/``sendto``/``sendmsg``,
    ``socket.create_connection``, the five resolvers in :data:`DNS_RESOLVERS`,
    ``_overlapped.ConnectEx`` on Windows, every factory in
    :data:`GRPC_CHANNEL_FACTORIES` together with ``grpc._channel.Channel``, and
    the entry points in :data:`CHILD_PROCESS_FACTORIES`.

    Allowed: an endpoint recorded in :data:`_OWNED_ENDPOINTS`, meaning a live
    socket in this process bound that exact ``(family, protocol, address)`` -
    which is what asyncio's ``ProactorEventLoop`` self-pipe and starlette's
    ``TestClient`` blocking portal open. A loopback address alone is not allowed,
    and neither is an ``AF_UNIX`` path this process did not bind. Resolving a
    loopback name is allowed; whether the connect that follows is admitted is
    decided by the endpoint, not by the name.

    Yields the guard, whose ``refuse`` method a test may use to assert the error
    text.
    """
    _EGRESS_GUARD.test_id = request.node.nodeid
    try:
        yield _EGRESS_GUARD
    finally:
        _EGRESS_GUARD.test_id = None


# --------------------------------------------------------------------------- #
# Configuration fixtures.
# --------------------------------------------------------------------------- #


@pytest.fixture
def pinned_settings_env():
    """Return the environment values the prologue pinned, name to value.

    A copy of :data:`DEFAULTED_SETTINGS_ENV`, so a test cannot mutate the
    mapping the prologue applied. The suite covering ``app/core/config.py``
    reads it to assert that the values behind its singleton assertions were
    positively established, rather than asserting that the surrounding
    environment happened to be empty.
    """
    return dict(DEFAULTED_SETTINGS_ENV)


# --------------------------------------------------------------------------- #
# Data-access boundary fixtures.
# --------------------------------------------------------------------------- #


@pytest.fixture
def firestore_client():
    """Yield a ``MagicMock`` standing in for the Firestore client.

    ``app.db.firestore.get_db`` is patched to return the mock, which covers
    the whole ``add_tweet`` / ``get_tweet`` / ``update_tweet`` surface
    without a real client: unpatched, ``get_db`` resolves credentials and
    constructs one.

    Patching rebinds the name, so :func:`_import_get_db_consumers` runs
    first and every module that captured the function object holds the real
    one.
    """
    firestore = importlib.import_module("app.db.firestore")
    _import_get_db_consumers()
    client = MagicMock(name="firestore_client")
    with patch.object(firestore, "get_db", return_value=client):
        yield client


@pytest.fixture
def firestore_client_constructor():
    """Patch ``app.db.firestore.Client`` and yield the stand-in constructor.

    The counterpart of :func:`firestore_client`: that fixture replaces ``get_db``,
    so no test using it executes the function's body. This one leaves ``get_db``
    in place and replaces the client class it constructs, which is what makes the
    body assertable without a real client.

    The constructor's ``return_value`` is a ``MagicMock`` specified against the
    real ``google.cloud.firestore.Client``, so the object handed back has that
    class's attribute surface and nothing more - reading an attribute the real
    client does not define raises ``AttributeError`` exactly as production would.

    Credential resolution is already neutralised for every test by
    :func:`neutralize_google_credentials`, which patches the ``default`` name on
    this module as well as on ``google.auth``.

    Yields the patched ``Client`` mock, whose ``call_args`` carries the arguments
    ``get_db`` passed and whose ``return_value`` is the client it returned.
    """
    firestore = importlib.import_module("app.db.firestore")
    from google.cloud.firestore import Client as RealClient

    constructor = MagicMock(name="firestore_Client")
    constructor.return_value = MagicMock(spec=RealClient, name="constructed_client")
    with patch.object(firestore, "Client", constructor):
        yield constructor


@pytest.fixture
def bigquery_settings():
    """Replace ``app.db.bigquery.Settings`` with a project-carrying stand-in.

    ``app/db/bigquery.py`` reads ``Settings.GOOGLE_CLOUD_PROJECT`` as a
    *class* attribute twice: once in ``get_bq_client`` and again in the
    ``table_id`` f-string.  pydantic v1 strips declared fields from the class
    namespace, so both reads raise ``AttributeError`` and ``get_bq_client``,
    ``run_query`` and ``insert_tweet_analytics`` are unreachable without this
    substitution.  The second read happens after ``get_bq_client`` has
    returned, so the stand-in stays in place for the whole call.

    Yields the :class:`types.SimpleNamespace` stand-in, whose
    ``GOOGLE_CLOUD_PROJECT`` is :data:`FAKE_PROJECT`.
    """
    bigquery = importlib.import_module("app.db.bigquery")
    stand_in = SimpleNamespace(GOOGLE_CLOUD_PROJECT=FAKE_PROJECT)
    with patch.object(bigquery, "Settings", stand_in):
        yield stand_in


# --------------------------------------------------------------------------- #
# Module fixtures.  Each installs, through :func:`_install_missing_symbol`, the
# stand-ins its import graph needs, on the module that defines the name and on
# every already-loaded module that captured it.
#
# Invariant: only ``app.tasks.response_generator`` is evicted from
# ``sys.modules``.  ``app.db.firestore``, ``app.schema.tweet``,
# ``app.core.config``, ``app.api.routes.tweets`` and ``app.main`` stay cached
# for the whole session, and the per-test isolation those cached modules need
# comes from rebinding their shimmed symbols rather than from reloading them.
# See ``docs/testing/DECISION-LOG.md`` §10, row D106.
# --------------------------------------------------------------------------- #


@pytest.fixture
def tweet_processor_module():
    """Import and yield ``app.tasks.tweet_processor`` under its shim.

    The module imports ``LLMService`` from ``app.services.llm_service``,
    which exposes only the free function ``generate_response``, and
    instantiates it, so the shim has to be a class.

    The shim installed here is :class:`unittest.mock.MagicMock` itself, which is
    *permissive* rather than fail-closed — one of only two fixtures in this module
    that is. What that makes observable: ``on_status`` line 32 feeds
    ``self.llm_service.calculate_doubt_rating(text)`` straight into
    ``Tweet(doubt_rating=...)``, and a ``MagicMock`` coerces to ``1.0`` through
    ``__float__``, so a status that clears the popularity gate reaches the schema
    and raises a pydantic ``ValidationError`` carrying exactly the eight field
    names the schema declares and the listener never supplies.

    See ``docs/testing/DECISION-LOG.md`` row D106.

    The shim is written to ``app.tasks.tweet_processor`` as well as to the
    defining module, because ``app.main``'s import graph may already have bound
    the fail-closed sentinel there; on exit the module is set back to it.
    """
    with _install_missing_symbol("LLMService", MagicMock):
        yield importlib.import_module("app.tasks.tweet_processor")


@pytest.fixture
def response_generator_module():
    """Import and yield a freshly loaded ``app.tasks.response_generator``.

    Two shims are needed for the module to load: ``add_response``, which
    ``app.db.firestore`` does not define, and ``LLMService``.

    Line 7 executes ``llm_service = LLMService()`` at module scope, so the
    module is evicted from :data:`sys.modules` before and after the test and
    every test receives its own ``MagicMock`` instance rather than sharing one
    whose call counts depend on execution order.

    That module-scope construction is also why this is the second of the two
    fixtures installing permissive shims: the fail-closed ``LLMService`` refuses
    at line 7 and the module would not import at all. The eviction on exit means
    nothing permissive survives — there is no cached consumer left to reset.
    """
    with _install_missing_symbol(
        "add_response", MagicMock(name="add_response")
    ), _install_missing_symbol("LLMService", MagicMock):
        sys.modules.pop("app.tasks.response_generator", None)
        try:
            yield importlib.import_module("app.tasks.response_generator")
        finally:
            sys.modules.pop("app.tasks.response_generator", None)


@pytest.fixture
def app_module():
    """Import and yield ``app.main`` with the three shims it needs.

    ``verify_token`` on ``app.core.security``, ``TwitterService`` on
    ``app.services.twitter_service`` and ``LLMService`` on
    ``app.services.llm_service``: each is imported inside ``app.main``'s
    graph and defined by no production module.  The ``verify_token`` shim is
    also what makes ``app.api.dependencies`` importable, and all three stay
    installed for the whole test, so a test body may import that module
    itself.

    * ``verify_token`` on ``app.core.security`` - imported by
      ``app/api/dependencies.py`` line 3.  That module exposes only
      ``create_access_token``, ``verify_password``, ``get_password_hash`` and
      ``pwd_context``.
    * ``TwitterService`` on ``app.services.twitter_service`` - imported by
      ``app/api/routes/tweets.py`` line 6.  That module exposes only
      ``TwitterStreamListener`` and ``start_twitter_stream``.
    * ``LLMService`` on ``app.services.llm_service`` - imported by
      ``app/api/routes/tweets.py`` line 7 and by
      ``app/tasks/tweet_processor.py`` line 4, which ``app/main.py`` line 5
      pulls in.

    All three are fail-closed: each raises
    :class:`MissingProductionSymbolError` on every call or construction, so no
    request can succeed against one and no bearer token is authorised. A test
    wanting a particular result patches the attribute on the module it is
    exercising.

    The ``verify_token`` shim also makes ``app.api.dependencies`` importable, so
    the suite covering that module consumes this fixture. Calling that shim
    **raises**; it does not return ``None``. So ``get_current_user`` reaches
    neither its 401 path nor its success path until a test replaces the stand-in,
    and ``backend/tests/unit/test_api_dependencies.py`` asserts that raise
    directly. A test asserting the 401 or an authenticated result patches in its
    own stand-in and sets ``return_value`` on it.

    ``app/main.py`` runs ``configure_cors(app)`` and ``include_routers(app)``
    at lines 41 and 42, so the module is left cached and the returned
    application is wired exactly once. Because those modules are never evicted,
    each shim is written to them directly and reset to the fail-closed sentinel
    on teardown rather than being left as installed.

    The shims stay installed for the duration of the test on the exporting
    modules and on ``app.api.dependencies`` and ``app.api.routes.tweets``,
    which copied the names at their own import time, so a test body may import
    ``app.api.dependencies`` itself and observe the same stand-ins. Each is
    replaced by a stateless fail-closed value when the test ends.
    """
    _import_get_db_consumers()
    with _application_shims():
        yield importlib.import_module("app.main")


# Clock control.


@pytest.fixture
def frozen_clock():
    """Freeze the clock at :data:`FROZEN_INSTANT` -- 2024-01-01 UTC.

    Every module in :data:`PRE_FREEZE_IMPORTS` is imported before the
    freeze, so no class deriving from ``datetime.date`` is defined against
    freezegun's ``FakeDate``.

    Yields the freezegun ``FrozenDateTimeFactory``, whose ``tick`` and
    ``move_to`` advance the frozen instant.
    """
    for module_name in PRE_FREEZE_IMPORTS:
        importlib.import_module(module_name)
    with freeze_time(FROZEN_INSTANT) as frozen:
        yield frozen

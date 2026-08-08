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
    default are assigned placeholders; every defaulted one, plus the two fields
    production reads but never declares, is removed so the declared default
    governs.  Assignment is unconditional, so no ambient value can win.

Deny-by-default egress, from before collection until after teardown
    Connect, datagram send, DNS resolution, the Windows overlapped connector,
    gRPC channel construction and child-process creation are refused unless the
    target is a socket this process itself owns - see :func:`_is_local_address`.

Fail-closed shims
    A symbol production imports but never defines is stood in for by a value
    that *refuses*.  Each shim is installed on the defining module and on every
    already-loaded module that captured it, and reset to the sentinel on exit.
    Every such shim lives here and nowhere else, so a test can neither install
    its own nor leak one into a later test.

Nothing survives the run
    :func:`pytest_unconfigure` restores the environment, the credential patch,
    ``builtins.Optional``, the logging record factory and the socket guard.

Contents
--------
Module-scope prologue
    Snapshots and forces the managed ``Settings`` variables, points
    ``GOOGLE_APPLICATION_CREDENTIALS`` at an absent path, installs the
    ``Optional`` shim, neutralises ambient Google credentials, installs the
    egress guard.
Configuration hooks
    :func:`pytest_configure` adds the child-process guard;
    :func:`pytest_unconfigure` releases every global mutation.
Test correlation
    Puts ``test_id`` and ``correlation_id`` on every log record, which is what
    the log formats in ``backend/pytest.ini`` print.
Autouse fixtures
    :func:`verify_settings_singletons`, :func:`neutralize_google_credentials`,
    :func:`block_network_access`.
Named fixtures
    :func:`pinned_settings_env`, :func:`firestore_client`,
    :func:`bigquery_settings`, :func:`tweet_processor_module`,
    :func:`response_generator_module`, :func:`app_module`,
    :func:`frozen_clock`.

Reasoning for every choice in this module: ``docs/testing/DECISION-LOG.md``
rows D25, D104, D105, D106, D121, D134 and D135.
``docs/testing/TRACEABILITY-MATRIX.md`` records the construct each fixture
covers.
"""

import builtins
import contextlib
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
import typing
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
#: ``NOTION_API_KEY`` is ``Optional[str] = None`` and is deliberately absent.
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

#: ``Settings`` fields that carry a declared default. Every one is *removed*
#: from the environment by the prologue rather than assigned a test value:
#: pydantic v1 resolves a field from ``os.environ`` before falling back to its
#: default, so an ambient variable named after one of these would decide the
#: value the suites assert against — a shell exporting ``POPULARITY_THRESHOLD``
#: would rewrite the popularity boundary matrix's oracle. Removing them makes
#: the declared default the only possible source. ``NOTION_API_KEY`` is here
#: too, which additionally keeps a real Notion key out of ``settings``.
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
#: read off ``settings`` although ``Settings`` declares neither. They are removed
#: for the same reason as :data:`DEFAULTED_SETTINGS_FIELDS`: a real consumer
#: secret must not be reachable from a test process. The suites covering those
#: modules supply them with ``monkeypatch``.
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

#: Loopback ports this process bound, recorded by the guard on
#: ``socket.socket.bind`` and read by :func:`_is_local_address`.  A loopback
#: *port* belongs to whichever process bound it, so admitting the whole
#: loopback interface would admit every other service on this host - under
#: parallel execution, another checkout's dev server or application process.
#: Only a port this interpreter bound itself is a socket the suite owns.
#:
#: Written and read under :data:`_BOUND_PORTS_LOCK`; a port is never removed,
#: because a closed port cannot be reached and re-recording is idempotent.
_PROCESS_BOUND_PORTS = set()

#: Serialises access to :data:`_PROCESS_BOUND_PORTS`.  ``socket.bind`` is
#: reachable from any thread, and starlette's ``TestClient`` runs its event
#: loop in one.
_BOUND_PORTS_LOCK = threading.Lock()

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

#: ``(module, attribute)`` shell entry points refused while a test is running.
#: A child process is the one egress path invisible to every guard above, since
#: its sockets belong to another process.  :class:`subprocess.Popen` is guarded
#: at ``__init__`` rather than by replacing the class, so the type stays intact
#: for anything that inspects it; ``os.popen`` needs no entry because it is
#: implemented on top of ``Popen``.
CHILD_PROCESS_FACTORIES = (("os", "system"),)

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
    :func:`_is_local_address`, which also requires the port to be one this
    process bound.
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


def _record_bound_port(sock):
    """Record the loopback port ``sock`` is bound to, if it has one.

    Called after a successful ``bind``, so the port is read from
    ``getsockname()`` rather than from the requested address: a bind to port
    ``0`` - which is what :func:`socket.socketpair` and every ephemeral listener
    ask for - is only assigned its real port by the kernel.
    """
    try:
        name = sock.getsockname()
    except OSError:
        return
    if not isinstance(name, tuple) or len(name) < 2:
        return
    host, port = name[0], name[1]
    if not isinstance(port, int) or port <= 0 or not _is_local_host(host):
        return
    with _BOUND_PORTS_LOCK:
        _PROCESS_BOUND_PORTS.add(port)


def _is_port_owned_by_this_process(port):
    """Return ``True`` when this process bound ``port`` on a loopback address."""
    if not isinstance(port, int):
        return False
    with _BOUND_PORTS_LOCK:
        return port in _PROCESS_BOUND_PORTS


def _is_local_address(sock, address):
    """Return ``True`` when ``address`` is a socket this process itself owns.

    Three admissions, and nothing else:

    * an ``AF_UNIX`` socket, which is local by construction and has no port;
    * an address with no port component, which cannot be a TCP or UDP target;
    * a loopback host on a port recorded in :data:`_PROCESS_BOUND_PORTS`.

    A loopback host on any other port is refused. That is the difference between
    "cannot leave the machine" and "belongs to this test run": a neighbouring
    checkout's dev server, an application process or another user's service all
    listen on this host, and reaching one is neither offline nor deterministic.
    """
    unix_family = getattr(socket, "AF_UNIX", None)
    family = getattr(sock, "family", None)
    if unix_family is not None and family == unix_family:
        return True
    if not isinstance(address, tuple) or not address:
        return False
    if not _is_local_host(address[0]):
        return False
    if len(address) < 2:
        return True
    return _is_port_owned_by_this_process(address[1])


class _EgressGuard:
    """Refuses every network operation whose target this process does not own.

    Installed by the module-scope prologue - the earliest point a conftest can
    act, and before collection imports the two production modules that build a
    Google Cloud ``Client()`` at module scope.  Released only by
    :func:`pytest_unconfigure`, so a thread that outlives the test that started
    it is still refused during teardown.

    ``test_id`` is set by :func:`block_network_access` for the duration of each
    test and reported in the error, so a refusal names the test that caused it.
    Outside a test the subject is reported as ``collection``.

    See ``docs/testing/DECISION-LOG.md`` rows D25, D105 and D121.
    """

    def __init__(self):
        self._patchers = []
        self.test_id = None

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
                subject=self.test_id or "collection",
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
        """Record the loopback port a successful ``bind`` assigned.

        Binding is not egress, so nothing is refused here. This is what makes a
        later connect to that port admissible: :func:`_is_local_address` admits a
        loopback target only when this process bound the port itself, and
        :func:`socket.socketpair` - which asyncio's proactor self-pipe and
        starlette's ``TestClient`` portal both reach - binds a listener on an
        ephemeral loopback port before connecting to it.
        """

        def guarded(sock, address, *args, **kwargs):
            result = real(sock, address, *args, **kwargs)
            _record_bound_port(sock)
            return result

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

    def _refuse_inside_a_test(self, name, real):
        """Return a callable that refuses only while a test is executing.

        Used for the child-process entry points only, because on Windows the
        standard library itself shells out - ``platform.uname()`` runs
        ``cmd /c ver`` - from module-scope imports and from pytest's own JUnit
        reporter.  The prologue warms that cache, and this narrowing keeps a
        benign spawn from pytest's machinery outside any test from failing a
        run.  Every socket, datagram, resolver and gRPC guard stays
        unconditional.

        See ``docs/testing/DECISION-LOG.md`` row D105.
        """

        def guarded(*args, **kwargs):
            if self.test_id is None:
                return real(*args, **kwargs)
            detail = args[0] if args else None
            raise self.refuse(name, detail)

        return guarded

    def _refuse_construction_inside_a_test(self, name, real):
        """As :meth:`_refuse_inside_a_test`, for an ``__init__`` replacement."""

        def guarded(instance, *args, **kwargs):
            if self.test_id is None:
                return real(instance, *args, **kwargs)
            detail = args[0] if args else None
            raise self.refuse(name, detail)

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

        The bind recorder goes first, so no ephemeral loopback port can be bound
        between installing the connect guards and installing it.
        """
        bind_patcher = patch.object(
            socket.socket, "bind", self._guard_bind(socket.socket.bind)
        )
        bind_patcher.start()
        self._patchers.append(bind_patcher)

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
        """Refuse child-process creation; see :data:`CHILD_PROCESS_FACTORIES`."""
        for module_name, attribute in CHILD_PROCESS_FACTORIES:
            self._add(module_name, attribute, self._refuse_inside_a_test)
        popen_patcher = patch.object(
            subprocess.Popen,
            "__init__",
            self._refuse_construction_inside_a_test(
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

# Unconditional assignment, not setdefault: an ambient real credential must not
# be able to win, because a suite running against one is neither deterministic
# nor offline.
for _setting_name, _setting_value in REQUIRED_SETTINGS_ENV.items():
    os.environ[_setting_name] = _setting_value
del _setting_name, _setting_value

# Pinning, not removal: pydantic v1 reads os.environ *before* the ``.env`` file
# named by Settings.Config.env_file, so assigning each declared default is what
# makes the singleton independent of a .env on disk as well as of an ambient
# value.  Removing the name would leave a .env free to decide it.
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
_BUILTINS_HAD_OPTIONAL = hasattr(builtins, "Optional")
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

# Populate platform's uname cache while no guard is installed. On Windows
# ``platform.uname()`` obtains the OS version by running ``cmd /c ver`` in a
# child process, and both ``platform.system()`` and ``platform.node()`` reach it.
# This one call caches the result for the whole process, so the child-process
# guard below never sees a spawn the standard library itself needed.
# See ``docs/testing/DECISION-LOG.md`` row D105.
platform.uname()

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
#: carry on the singleton. Each name is removed from the environment by the
#: prologue, so the declared default at ``app/core/config.py`` lines 22-25 is the
#: only possible source and these are exactly those defaults.
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


def _settings_normalisation_failures(settings):
    """Return a message per field whose value is not the one assigned above.

    ``settings`` is the singleton ``app/core/config.py`` line 32 builds, which
    is the object production modules read. Each expected value comes from
    :data:`REQUIRED_SETTINGS_ENV` or :data:`TESTABILITY_SETTINGS_VALUES`, and
    every name in :data:`DEFAULTED_SETTINGS_ENV_NAMES` is additionally required
    to be absent from the environment so its declared default governs.
    """
    failures = []
    expected_values = dict(REQUIRED_SETTINGS_ENV)
    expected_values.update(TESTABILITY_SETTINGS_VALUES)
    for field_name, expected in expected_values.items():
        actual = getattr(settings, field_name, None)
        if actual != expected:
            failures.append(
                "settings.{field} is {actual!r}; the suite assigns "
                "{expected!r}".format(
                    field=field_name, actual=actual, expected=expected
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
    seeded variable, no credential patch, no injected builtin, no replaced
    logging factory and no socket guard survives.
    """
    _EGRESS_GUARD.release()

    # Installed at this module's scope; a run inside a larger session - an IDE
    # test runner, or a second pytest invocation in one interpreter - would
    # otherwise keep stamping `test_id` and `correlation_id` onto every record
    # any code in the process emits.
    logging.setLogRecordFactory(_BASE_LOG_RECORD_FACTORY)

    with contextlib.suppress(RuntimeError):
        _AMBIENT_CREDENTIAL_PATCH.stop()
    _restore_environment()

    if not _BUILTINS_HAD_OPTIONAL:
        # The shim exists only because app/core/security.py line 11 needs it;
        # leaving it behind would let unrelated code in this interpreter resolve
        # a name Python does not define.
        with contextlib.suppress(AttributeError):
            delattr(builtins, "Optional")


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
_current_test_id = SESSION_TEST_ID


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
    record.test_id = _current_test_id
    record.correlation_id = correlation_id_for(_current_test_id)
    return record


logging.setLogRecordFactory(_log_record_factory)


def pytest_runtest_logstart(nodeid, location):
    """Attribute subsequent log records to the test that is starting."""
    global _current_test_id
    _current_test_id = nodeid


def pytest_runtest_logfinish(nodeid, location):
    """Return attribution to the session once a test has finished."""
    global _current_test_id
    _current_test_id = SESSION_TEST_ID


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
    setattr(definer, symbol_name, value)
    for consumer in _loaded_consumers(symbol_name):
        setattr(consumer, symbol_name, value)
    try:
        yield value
    finally:
        if had_attribute:
            setattr(definer, symbol_name, previous)
        else:
            delattr(definer, symbol_name)
        for consumer in _loaded_consumers(symbol_name):
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

    All three refuse rather than succeed. Nothing in the import graph uses any
    of them at import time — ``TwitterService`` is imported and never referenced
    again, and both ``LLMService()`` calls sit inside function bodies — so the
    application still assembles, while a request that reaches one fails loudly.
    ``verify_token`` is the reason this matters: a truthy stand-in would make
    ``app/api/dependencies.py`` line 13 return a principal for any token at all.

    A test that needs a controlled result patches the attribute on the module
    under test; ``backend/tests/unit/test_api_dependencies.py`` shows the idiom.
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
    """Assert every required field on ``settings`` holds its test value."""
    for field_name, expected in REQUIRED_SETTINGS_ENV.items():
        actual = getattr(settings, field_name)
        assert actual == expected, (
            "{description}.{field} is {actual!r}; the suite requires the "
            "synthetic value {expected!r}. An ambient environment variable or a "
            "backend/.env file is supplying a real one.".format(
                description=description,
                field=field_name,
                actual=actual,
                expected=expected,
            )
        )
    assert settings.NOTION_API_KEY is None, (
        "{description}.NOTION_API_KEY is not None; NOTION_API_KEY is set in the "
        "environment or in backend/.env.".format(description=description)
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

    Refused: ``socket.socket.connect``/``connect_ex``/``sendto``,
    ``socket.create_connection``, the five resolvers in :data:`DNS_RESOLVERS`,
    ``_overlapped.ConnectEx`` on Windows, every factory in
    :data:`GRPC_CHANNEL_FACTORIES` together with ``grpc._channel.Channel``, and
    the entry points in :data:`CHILD_PROCESS_FACTORIES`.

    Allowed: loopback addresses and names, and ``AF_UNIX`` sockets. asyncio's
    ``ProactorEventLoop`` self-pipe and starlette's ``TestClient`` blocking
    portal both open loopback sockets in-process, and neither can reach a host
    outside the machine.

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

    This is one of only two fixtures that install a *permissive* shim instead of
    the fail-closed default, and the reason is the behaviour under test. The
    shim is :class:`unittest.mock.MagicMock` itself. ``on_status`` line 32 feeds
    ``self.llm_service.calculate_doubt_rating(text)`` straight into
    ``Tweet(doubt_rating=...)``, and a ``MagicMock`` coerces to ``1.0`` through
    ``__float__``, so a status that clears the popularity gate raises a
    pydantic ``ValidationError`` carrying exactly the eight field names the
    schema declares and the listener never supplies. A fail-closed sentinel
    would abort in ``TweetStreamListener.__init__`` at line 14 and that
    documented outcome would become unobservable.

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

    All three are fail-closed: each refuses every call or construction, so no
    request can succeed against one. That is what keeps this fixture from
    authorising an arbitrary bearer token — ``app/api/dependencies.py`` line 13
    returns whatever ``verify_token`` produced, so a permissive stand-in is an
    open door. A test wanting a particular result patches the attribute on the
    module it is exercising.

    The ``verify_token`` shim also makes ``app.api.dependencies`` importable,
    so the suite covering that module consumes this fixture. That shim returns
    ``None`` until a test configures it, which sends
    ``get_current_user`` down the 401 path at ``app/api/dependencies.py`` line
    12; a test asserting an authenticated result sets ``return_value`` on the
    stand-in it patches in.

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

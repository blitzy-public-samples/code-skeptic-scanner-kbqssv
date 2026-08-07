"""Shared test infrastructure for the Code Skeptic Scanner backend suite.

Ordering in this module is load-bearing. ``app/core/config.py`` executes
``settings = Settings()`` at module scope, and seven further production modules
construct their own module-scope ``Settings()`` at import time
(``app/main.py``, ``app/core/security.py``,
``app/services/twitter_service.py``, ``app/services/llm_service.py``,
``app/services/analytics_service.py``, ``app/tasks/tweet_processor.py`` and
``app/tasks/response_generator.py``). pytest imports every test module during
collection, which happens before any fixture runs, so the environment seeding,
the ``Optional`` shim and the credential neutralisation below are performed at
*this module's* scope.

No ``app.*`` module is imported at this module's scope. Every production module
is imported lazily inside a fixture through :func:`importlib.import_module`,
which guarantees the prologue has already executed.

Contents
--------
Module-scope prologue
    Seeds the eight ``Settings`` fields declared without a default, points
    ``GOOGLE_APPLICATION_CREDENTIALS`` at an absent path, installs the
    ``Optional`` shim that makes ``app/core/security.py`` importable, and
    neutralises ambient Google credential resolution.
Autouse fixtures
    :func:`neutralize_google_credentials`, :func:`block_network_access`.
Named fixtures
    :func:`firestore_client`, :func:`bigquery_settings`,
    :func:`tweet_processor_module`, :func:`response_generator_module`,
    :func:`app_module`, :func:`frozen_clock`.

Every shim for a symbol that production code imports but never defines lives in
this module and nowhere else, so a test can neither install its own nor leak
one into a later test.
"""

import builtins
import contextlib
import importlib
import os
import socket
import sys
import typing
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

# --------------------------------------------------------------------------- #
# Deterministic values shared by the whole suite.
# --------------------------------------------------------------------------- #

#: Project identifier returned by every credential and settings stand-in.
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

#: Path assigned to ``GOOGLE_APPLICATION_CREDENTIALS``.  It never exists, so no
#: key file can be read even if :func:`neutralize_google_credentials` is
#: bypassed.
ABSENT_CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_blitzy_absent_credentials.json",
)

#: Host strings that cannot leave the machine.  See :func:`_is_local_address`.
LOOPBACK_HOSTS = frozenset(
    {"127.0.0.1", "::1", "localhost", "ip6-localhost", "0.0.0.0", "::", ""}
)

#: ``(module, attribute)`` channel factories blocked by
#: :func:`block_network_access`. ``google-cloud-firestore`` talks gRPC, whose
#: sockets are opened by the C core rather than through ``socket.socket``, so a
#: guard on ``connect`` alone does not stop it: an unpatched ``get_tweet``
#: reaches Google Cloud for real and returns ``NotFound: 404 The database
#: (default) does not exist``. Channel construction is the Python-level entry
#: point to that transport. Targets absent from the installed distribution are
#: skipped.
GRPC_CHANNEL_FACTORIES = (
    ("grpc", "secure_channel"),
    ("grpc", "insecure_channel"),
    ("grpc.aio", "secure_channel"),
    ("grpc.aio", "insecure_channel"),
    ("google.api_core.grpc_helpers", "create_channel"),
    ("google.api_core.grpc_helpers_async", "create_channel"),
)

#: Modules that bind ``get_db`` with ``from app.db.firestore import get_db``
#: and therefore capture the function *object* at their own import time.
#: ``app/api/routes/tweets.py`` puts that object in three ``Depends(get_db)``
#: defaults, and ``app.dependency_overrides`` is keyed on it by identity, so
#: the capture has to happen while ``app.db.firestore.get_db`` is the real
#: function. :func:`_import_get_db_consumers` guarantees that regardless of
#: fixture order.
GET_DB_CONSUMERS = ("app.main", "app.api.dependencies")

#: Modules imported before :func:`frozen_clock` freezes the clock. ``pydantic``
#: declares ``class ConstrainedDate(date, metaclass=ConstrainedNumberMeta)`` at
#: ``types.py`` line 1181, and while freezegun is active ``datetime.date`` is
#: ``FakeDate``, whose metaclass differs. A first import under a frozen clock
#: therefore raises ``TypeError: metaclass conflict`` and leaves ``pydantic``
#: half-initialised in :data:`sys.modules` for the rest of the process, which
#: surfaces whenever a worker's first test is a frozen-clock one.
PRE_FREEZE_IMPORTS = ("pydantic", "app.core.config", "app.core.security")


class UnmockedNetworkAccessError(RuntimeError):
    """Raised when a test opens a socket to an address outside the machine.

    ``google.auth.default()`` resolves against ambient credentials in some
    environments and both stream starters terminate in
    ``stream.filter(track=...)``, so an unpatched boundary reaches live
    infrastructure rather than failing offline.  :func:`block_network_access`
    turns that into this error.
    """


# --------------------------------------------------------------------------- #
# Module-scope prologue.  Executed on import, before any ``app.*`` module.
# --------------------------------------------------------------------------- #

for _setting_name, _setting_value in REQUIRED_SETTINGS_ENV.items():
    # setdefault: a value deliberately exported by the caller wins.
    os.environ.setdefault(_setting_name, _setting_value)
del _setting_name, _setting_value

# Unconditional: neutralisation must not be defeatable by an ambient value.
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ABSENT_CREDENTIALS_PATH

# ``app/core/security.py`` annotates ``expires_delta: Optional[timedelta]`` at
# line 11 without importing ``Optional``, so importing it raises
# ``NameError: name 'Optional' is not defined``.  ``app/api/dependencies.py``
# imports from that module and inherits the failure.
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


#: ``app/db/firestore.py`` and ``app/db/bigquery.py`` construct a Google Cloud
#: ``Client()`` at module scope, and ``GOOGLE_APPLICATION_CREDENTIALS`` above
#: points at an absent file, which makes ``google.auth.default()`` raise
#: ``DefaultCredentialsError``. Both modules are imported at module scope by
#: the suites that cover them, so the neutralisation is in force from this
#: module's import onward, which is before collection imports either of them.
#: That ordering also means ``app/db/firestore.py`` line 2,
#: ``from google.auth import default``, binds the stand-in.
_AMBIENT_CREDENTIAL_PATCH = patch(
    "google.auth.default", new=_fake_google_auth_default
)
_AMBIENT_CREDENTIAL_PATCH.start()


def pytest_unconfigure(config):
    """Release the module-scope credential neutraliser at the end."""
    with contextlib.suppress(RuntimeError):
        _AMBIENT_CREDENTIAL_PATCH.stop()


# --------------------------------------------------------------------------- #
# Shim installation.
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _install_missing_symbol(module, name, replacement):
    """Bind ``name`` to ``replacement`` on ``module`` in a block.

    On exit the previous binding is restored, or the attribute is deleted when
    ``module`` had none, so no shim outlives the fixture that installed it and
    no later test can pass against a leftover.

    Yields ``replacement``.
    """
    had_attribute = hasattr(module, name)
    previous = getattr(module, name, None)
    setattr(module, name, replacement)
    try:
        yield replacement
    finally:
        if had_attribute:
            setattr(module, name, previous)
        else:
            delattr(module, name)


# --------------------------------------------------------------------------- #
# Helpers used by the fixtures below.
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _application_shims():
    """Install the three shims ``app.main``'s import graph needs.

    Each stands in for a symbol production code imports but that no production
    module defines: ``verify_token`` on ``app.core.security``
    (``app/api/dependencies.py`` line 3), ``TwitterService`` on
    ``app.services.twitter_service`` (``app/api/routes/tweets.py`` line 6) and
    ``LLMService`` on ``app.services.llm_service``
    (``app/api/routes/tweets.py`` line 7 and ``app/tasks/tweet_processor.py``
    line 4, which ``app/main.py`` line 5 pulls in).
    """
    security = importlib.import_module("app.core.security")
    twitter_service = importlib.import_module("app.services.twitter_service")
    llm_service = importlib.import_module("app.services.llm_service")
    with _install_missing_symbol(
        security, "verify_token", MagicMock(name="verify_token")
    ), _install_missing_symbol(
        twitter_service, "TwitterService", MagicMock
    ), _install_missing_symbol(llm_service, "LLMService", MagicMock):
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


def _iter_grpc_channel_patchers(blocked):
    """Yield a ``patch.object`` for every installed target in
    :data:`GRPC_CHANNEL_FACTORIES`, replacing it with ``blocked``."""
    for module_name, attribute in GRPC_CHANNEL_FACTORIES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, attribute):
            yield patch.object(module, attribute, blocked)


def _is_local_address(sock, address):
    """Return ``True`` when ``address`` cannot leave the machine."""
    unix_family = getattr(socket, "AF_UNIX", None)
    family = getattr(sock, "family", None)
    if unix_family is not None and family == unix_family:
        return True
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if host is None:
        return True
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "ignore")
    if not isinstance(host, str):
        return False
    if host in LOOPBACK_HOSTS:
        return True
    return host.startswith("127.") or host == "::ffff:127.0.0.1"


# --------------------------------------------------------------------------- #
# Autouse fixtures.
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def neutralize_google_credentials():
    """Make Google credential resolution deterministic and offline.

    ``google.auth.default`` is replaced with a stand-in returning a
    ``MagicMock`` credential and the fixed project :data:`FAKE_PROJECT`.
    ``app/db/firestore.py`` line 2 binds ``default`` into its own namespace
    with ``from google.auth import default``, so that name is patched too
    whenever the module is already loaded.

    The stand-in returns a value rather than raising, so a code path that
    reaches a real client surfaces as an :class:`UnmockedNetworkAccessError`
    from :func:`block_network_access` rather than as a credential error.

    Yields the ``(credential, project)`` pair the stand-in returns.
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
    """Fail loudly when a test opens a socket that leaves the box.

    ``socket.socket.connect`` and ``socket.socket.connect_ex`` are replaced for
    the duration of each test and raise :class:`UnmockedNetworkAccessError`,
    naming the test, when the target is not local. This covers the ``requests``
    transport that ``tweepy`` 3.10, ``openai`` 0.27 and the Google metadata
    server client all use.

    Connections to loopback addresses and ``AF_UNIX`` sockets are passed
    through.  asyncio's ``ProactorEventLoop`` self-pipe and starlette's
    ``TestClient`` blocking portal both open loopback sockets in-process, and
    neither can reach a host outside the machine.

    Every gRPC channel factory in :data:`GRPC_CHANNEL_FACTORIES` is blocked as
    well, which is what stops ``google-cloud-firestore``: its transport is
    opened by the gRPC C core and never passes through ``socket.socket``.
    """
    test_id = request.node.nodeid

    def _refuse(operation, detail):
        return UnmockedNetworkAccessError(
            "{test} attempted an unmocked network call: "
            "{operation}({detail!r}). "
            "Patch the boundary the code under test uses instead, for example "
            "app.db.firestore.get_db, app.db.bigquery.Client, "
            "app.services.llm_service.Completion.create, or "
            "sys.modules['tweepy'].".format(
                test=test_id, operation=operation, detail=detail
            )
        )

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _make_socket_guard(operation, real_operation):
        def guarded(self, address):
            if _is_local_address(self, address):
                return real_operation(self, address)
            raise _refuse("socket." + operation, address)

        return guarded

    def _blocked_channel(target=None, *args, **kwargs):
        raise _refuse("grpc channel", target)

    socket.socket.connect = _make_socket_guard("connect", real_connect)
    socket.socket.connect_ex = _make_socket_guard(
        "connect_ex", real_connect_ex
    )
    try:
        with contextlib.ExitStack() as stack:
            for patcher in _iter_grpc_channel_patchers(_blocked_channel):
                stack.enter_context(patcher)
            yield
    finally:
        socket.socket.connect = real_connect
        socket.socket.connect_ex = real_connect_ex


# --------------------------------------------------------------------------- #
# Data-access boundary fixtures.
# --------------------------------------------------------------------------- #


@pytest.fixture
def firestore_client():
    """Yield a ``MagicMock`` standing in for the Firestore client.

    ``app.db.firestore.get_db`` is patched to return the mock, which exposes
    the whole ``add_tweet`` / ``get_tweet`` / ``update_tweet`` surface without
    a real client. ``get_db`` calls ``google.auth.default()`` and then
    constructs a ``Client``, so an unpatched call performs a genuine Google
    Cloud round trip.

    Replacing ``get_db`` rebinds the name, so :func:`_import_get_db_consumers`
    runs first and every module that captures the function object has already
    captured the real one.
    """
    firestore = importlib.import_module("app.db.firestore")
    _import_get_db_consumers()
    client = MagicMock(name="firestore_client")
    with patch.object(firestore, "get_db", return_value=client):
        yield client


@pytest.fixture
def bigquery_settings():
    """Replace ``app.db.bigquery.Settings`` with a project-carrying stand-in.

    ``app/db/bigquery.py`` reads ``Settings.GOOGLE_CLOUD_PROJECT`` as a *class*
    attribute at line 7 and again inside the ``table_id`` f-string at line 21.
    pydantic v1 strips declared fields from the class namespace, so both reads
    raise ``AttributeError: type object 'Settings' has no attribute
    'GOOGLE_CLOUD_PROJECT'`` and ``get_bq_client``, ``run_query`` and
    ``insert_tweet_analytics`` are unreachable without this substitution. The
    line 21 read happens after ``get_bq_client`` has already returned, so the
    stand-in has to be in place for the whole call.

    Yields the :class:`types.SimpleNamespace` stand-in, whose
    ``GOOGLE_CLOUD_PROJECT`` is :data:`FAKE_PROJECT`.
    """
    bigquery = importlib.import_module("app.db.bigquery")
    stand_in = SimpleNamespace(GOOGLE_CLOUD_PROJECT=FAKE_PROJECT)
    with patch.object(bigquery, "Settings", stand_in):
        yield stand_in


# --------------------------------------------------------------------------- #
# Module fixtures.  Each installs the shims its import graph needs.
#
# Only ``app.tasks.response_generator`` is evicted from ``sys.modules``.
# ``app.db.firestore``, ``app.schema.tweet``, ``app.core.config`` and
# ``app.api.routes.tweets`` stay cached: the integration layer keys
# ``app.dependency_overrides`` on the ``get_db`` function object captured when
# the router was imported and matches it by identity, re-importing
# ``app.core.config`` would create a second ``Settings`` singleton, and
# re-importing ``app.main`` would stack a second CORS middleware and a second
# copy of every router onto the application.
# --------------------------------------------------------------------------- #


@pytest.fixture
def tweet_processor_module():
    """Import and yield ``app.tasks.tweet_processor`` under its shim.

    ``app/tasks/tweet_processor.py`` line 4 imports ``LLMService`` from
    ``app.services.llm_service``, which exposes only the free function
    ``generate_response``; the class exists nowhere in the repository, so the
    module cannot be imported without the shim.  Line 10 annotates
    ``llm_service: LLMService`` in the class body and line 14 calls
    ``LLMService()``, so the shim must be a class.

    The shim is :class:`unittest.mock.MagicMock` itself. ``on_status`` line 32
    feeds ``self.llm_service.calculate_doubt_rating(text)`` straight into
    ``Tweet(doubt_rating=...)``, and a ``MagicMock`` coerces to ``1.0`` through
    ``__float__``, so a status that clears the popularity gate raises a
    pydantic ``ValidationError`` carrying exactly the eight field names the
    schema declares and the listener never supplies.
    """
    llm_service = importlib.import_module("app.services.llm_service")
    with _install_missing_symbol(llm_service, "LLMService", MagicMock):
        yield importlib.import_module("app.tasks.tweet_processor")


@pytest.fixture
def response_generator_module():
    """Import and yield a freshly loaded ``app.tasks.response_generator``.

    Two shims are required for the module to load.  Line 1 imports
    ``add_response`` from ``app.db.firestore``, which defines only ``get_db``,
    ``add_tweet``, ``get_tweet`` and ``update_tweet``; line 3 imports the
    non-existent ``LLMService``.

    Line 7 executes ``llm_service = LLMService()`` at module scope, so the
    module is evicted from :data:`sys.modules` before and after the test and
    every test receives its own ``MagicMock`` instance rather than sharing one
    whose call counts depend on execution order.
    """
    firestore = importlib.import_module("app.db.firestore")
    llm_service = importlib.import_module("app.services.llm_service")
    with _install_missing_symbol(
        firestore, "add_response", MagicMock(name="add_response")
    ), _install_missing_symbol(llm_service, "LLMService", MagicMock):
        sys.modules.pop("app.tasks.response_generator", None)
        try:
            yield importlib.import_module("app.tasks.response_generator")
        finally:
            sys.modules.pop("app.tasks.response_generator", None)


@pytest.fixture
def app_module():
    """Import and yield ``app.main`` with the three shims needed.

    Each shim stands in for a symbol that production code imports but that no
    production module defines:

    * ``verify_token`` on ``app.core.security`` — imported by
      ``app/api/dependencies.py`` line 3.  That module exposes only
      ``create_access_token``, ``verify_password``, ``get_password_hash`` and
      ``pwd_context``.
    * ``TwitterService`` on ``app.services.twitter_service`` — imported by
      ``app/api/routes/tweets.py`` line 6.  That module exposes only
      ``TwitterStreamListener`` and ``start_twitter_stream``.
    * ``LLMService`` on ``app.services.llm_service`` — imported by
      ``app/api/routes/tweets.py`` line 7 and by
      ``app/tasks/tweet_processor.py`` line 4, which ``app/main.py`` line 5
      pulls in.

    The ``verify_token`` shim also makes ``app.api.dependencies`` importable,
    so the suite covering that module consumes this fixture.

    ``app/main.py`` runs ``configure_cors(app)`` and ``include_routers(app)``
    at lines 41 and 42, so the module is left cached and the returned
    application is wired exactly once.

    The shims stay installed for the duration of the test, so a test body may
    import ``app.api.dependencies`` itself.
    """
    _import_get_db_consumers()
    with _application_shims():
        yield importlib.import_module("app.main")


# --------------------------------------------------------------------------- #
# Clock control.
# --------------------------------------------------------------------------- #


@pytest.fixture
def frozen_clock():
    """Freeze the clock at :data:`FROZEN_INSTANT`, ``2024-01-01 00:00:00`` UTC.

    That instant is epoch 1704067200, and the 15-minute default hardcoded at
    ``app/core/security.py`` line 16 puts a token's ``exp`` claim at
    1704068100.

    Every module in :data:`PRE_FREEZE_IMPORTS` is imported before the clock is
    frozen, so no class deriving from ``datetime.date`` is defined against
    freezegun's ``FakeDate``.

    Yields the freezegun ``FrozenDateTimeFactory``, whose ``tick`` and
    ``move_to`` methods advance the frozen instant.
    """
    for module_name in PRE_FREEZE_IMPORTS:
        importlib.import_module(module_name)
    with freeze_time(FROZEN_INSTANT) as frozen:
        yield frozen

"""Fixtures for the integration layer of the Code Skeptic Scanner backend.

Turns the already-wired ``app.main.app`` object into a per-test HTTP client and
owns the ``app.dependency_overrides`` contract, including the teardown that
empties the override map after every test.  Requests travel over starlette's
in-process ASGI transport, and every fixture here is function-scoped.

Layer contract
--------------
Application object
    ``app/main.py`` runs ``configure_cors(app)`` and ``include_routers(app)``
    at lines 41 and 42, so the application is fully wired the moment the module
    is imported. :func:`integration_app` hands that same object out and calls
    neither function again, which keeps ``app.user_middleware`` a single
    ``CORSMiddleware`` entry long and every router included exactly once.
Lifecycle
    Both clients are constructed *without* being entered as context managers,
    so neither the ``startup`` handler registered at ``app/main.py`` line 26
    nor the ``shutdown`` handler at line 35 ever runs. The startup handler
    calls ``get_db()`` — which resolves Google credentials and constructs a
    Firestore ``Client`` — and then ``await start_tweet_stream()``, which
    blocks on a live Twitter stream. Each client is nevertheless closed on
    teardown, which releases its transport without running either handler.
Transport
    Requests travel over starlette's in-process ASGI transport, so serving a
    request opens no socket.
Dependency injection
    Data reaches a handler through :func:`override_get_db`, which keys
    ``app.dependency_overrides`` on ``app.db.firestore.get_db``.
Isolation
    Every fixture here is function-scoped, so no client, application override
    or stand-in is shared between tests and this layer's suites impose no
    ordering requirement on one another. The one object that *is* shared — the
    application built at ``app/main.py`` module scope, which is never
    re-imported — carries the ``dependency_overrides`` map, and
    :func:`reset_dependency_overrides` empties it before and after every test
    regardless of which fixtures that test named. Both clients are closed on
    teardown, so no ``httpx`` transport is left open behind a finished test.

Fixtures
--------
:func:`main_module`
    The imported ``app.main`` module.
:func:`integration_app`
    The ``FastAPI`` instance that module built at import.
:func:`reset_dependency_overrides`
    Autouse. Empties the shared override map on entry and on exit.
:func:`client`
    ``TestClient`` that re-raises an exception raised inside a handler, closed
    on teardown.
:func:`client_no_raise`
    ``TestClient`` that reports one as a ``500`` response instead, closed on
    teardown.
:func:`mock_db`
    Unprogrammed stand-in for the object ``Depends(get_db)`` yields.
:func:`override_get_db`
    Installs a stand-in and empties the override map on teardown.

Everything shared with the unit layer is consumed from the parent
``backend/tests/conftest.py`` and is not restated here: the five shims for
symbols production code imports but never defines (``Optional``,
``LLMService``, ``add_response``, ``verify_token`` and ``TwitterService``), the
seeded and pinned ``Settings`` environment variables, the autouse credential
neutraliser and the autouse network guard. This module installs no shim, seeds
no environment variable and defines no fixture whose name would shadow one of
the parent's.

Reasoning for the client lifecycle and the override contract:
``docs/testing/DECISION-LOG.md`` §10, row D107.
"""

import contextlib
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.db.firestore as firestore

# Application object.


@pytest.fixture
def main_module(app_module):
    """Return the imported ``app.main`` module.

    ``main_module.start_tweet_stream``, ``main_module.get_db`` and
    ``main_module.settings`` are the names ``app/main.py`` binds into its own
    namespace, which is the boundary a patch has to target for the handlers
    registered in the module to observe it.
    """
    return app_module


@pytest.fixture
def integration_app(main_module):
    """Return the ``FastAPI`` instance ``app.main`` built at import.

    ``app/main.py`` wires CORS and the four routers at its own module scope, so
    the application arrives with one ``CORSMiddleware`` entry and one copy of
    each router.  This fixture builds no second application and re-runs neither
    wiring function.

    Only ``app/api/routes/tweets.py`` contributes endpoints; the other three
    routers are bare, and no route carries the ``API_V1_STR`` prefix.
    """
    return main_module.app


# HTTP clients.  Neither is entered as a context manager, so the ``startup``
# handler -- which calls ``get_db()`` and then ``await
# start_tweet_stream()`` -- and the ``shutdown`` handler stay registered and
# never run.


@contextlib.contextmanager
def _closing_client(**client_options):
    """Yield a ``TestClient`` for ``integration_app`` and close it after.

    The client is constructed and yielded, never entered as a context manager,
    so the ``startup`` handler registered at ``app/main.py`` line 26 and the
    ``shutdown`` handler at line 35 stay registered and uninvoked.

    ``close()`` releases the underlying ``httpx`` transport and its connection
    pool. It is the counterpart of ``httpx.Client`` construction rather than of
    ``__enter__``, so calling it invokes no lifecycle handler either. It runs
    from a ``finally`` block, so a test that fails mid-request still releases
    the client.
    """
    client = TestClient(**client_options)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def client(integration_app):
    """Yield a ``TestClient`` that re-raises exceptions from a handler.

    The client is constructed and yielded, never entered as a context manager,
    so the ``startup`` and ``shutdown`` handlers stay registered but uninvoked.
    Teardown calls ``close()``, which releases the underlying ``httpx``
    transport and connection pool without touching the lifespan: it is
    ``__enter__`` that runs the startup handler, not construction, and
    ``close()`` is not ``__exit__``. Without it every test would leave a client
    open until the interpreter exited.

    ``raise_server_exceptions`` keeps its default of ``True``, so an exception
    raised inside a handler propagates out of the request call instead of being
    reported as a response, which is what lets a test name the exception type
    with ``pytest.raises``.

    Teardown calls ``close()``, which releases the underlying transport and its
    connection pool. ``close()`` is not ``__exit__``: it runs no lifecycle
    handler, so the startup handler stays uninvoked.
    """
    test_client = TestClient(integration_app)
    try:
        yield test_client
    finally:
        test_client.close()


@pytest.fixture
def client_no_raise(integration_app):
    """Yield a ``TestClient`` that reports a handler exception as a ``500``.

    Identical to :func:`client` apart from ``raise_server_exceptions=False``,
    which makes an unhandled exception inside a handler surface as a response
    with ``status_code == 500`` rather than propagating. This client is likewise
    never entered as a context manager, so no lifecycle handler runs, and it is
    closed on teardown for the same reason.
    """
    test_client = TestClient(integration_app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        test_client.close()


# Dependency injection.


@pytest.fixture
def mock_db():
    """Return an unprogrammed ``MagicMock`` standing in for the database.

    Each tweets handler drives a different call chain off the injected object,
    so a test programs only the attributes the endpoint under test reaches.
    Pass it to :func:`override_get_db` to install it.
    """
    return MagicMock(name="mock_db")


@pytest.fixture(autouse=True)
def reset_dependency_overrides(integration_app):
    """Empty ``app.dependency_overrides`` before and after every test here.

    ``app/main.py`` builds its ``FastAPI`` instance at module scope and the
    module is deliberately never re-imported, so that one object — and the
    override map hanging off it — outlives every test in this layer.
    :func:`override_get_db` clears the map on its own teardown, but only a test
    that *requests* that fixture gets the cleanup: a test installing an override
    directly on ``integration_app.dependency_overrides``, or one that fails part
    way through doing so, would leave an entry behind for whatever ran next.

    This fixture is autouse and unconditional, so the guarantee does not depend
    on which fixtures a test happens to name. Clearing on entry as well as on
    exit means a test is unaffected even by something that escaped a previous
    one, which also makes the order tests execute in irrelevant.

    It requests :func:`integration_app` rather than importing ``app.main``
    itself, because that module cannot be imported at all without the three
    shims the parent conftest's ``app_module`` fixture installs. Every test in
    this layer reaches the application through a client anyway, so nothing is
    imported here that a test was not going to import.

    Yields the override mapping, so a test may assert it is empty.
    """
    overrides = integration_app.dependency_overrides
    overrides.clear()
    try:
        yield overrides
    finally:
        overrides.clear()


@pytest.fixture
def override_get_db(integration_app):
    """Yield a callable that injects an object in place of ``get_db``::

        def test_lists_tweets(client, mock_db, override_get_db):
            override_get_db(mock_db)
            response = client.get("/tweets")

    ``dependency_overrides`` is keyed by object identity on the
    ``app.db.firestore.get_db`` the tweets router captured in its
    ``Depends(get_db)`` defaults at import.  The parent conftest imports that
    router while ``get_db`` is still the real function and leaves the module
    cached, so the ``firestore.get_db`` read here is that same object.

    Teardown clears the map unconditionally, since the application object
    outlives every test.  The fixture is not autouse, so a test needing no
    injected database simply does not request it.
    """

    def _override_get_db(db):
        integration_app.dependency_overrides[firestore.get_db] = lambda: db
        return db

    try:
        yield _override_get_db
    finally:
        integration_app.dependency_overrides.clear()

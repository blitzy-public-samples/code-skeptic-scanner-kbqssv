"""Fixtures for the integration layer of the Code Skeptic Scanner backend.

Turns the already-wired ``app.main.app`` object into a per-test HTTP client and
owns the ``app.dependency_overrides`` contract, including the teardown that
empties the override map after every test.

Layer contract
--------------
Application object
    ``app/main.py`` runs ``configure_cors(app)`` and ``include_routers(app)`` at
    its own module scope, so the application is fully wired the moment the module
    is imported.  :func:`integration_app` hands that same object out and calls
    neither function again, which keeps ``app.user_middleware`` one
    ``CORSMiddleware`` entry long and every router included exactly once.  Only
    ``app/api/routes/tweets.py`` contributes endpoints; the other three routers
    are bare, and no route carries the ``API_V1_STR`` prefix.
Lifecycle
    Neither client is entered as a context manager, so the ``startup`` handler at
    ``app/main.py`` line 26 - which calls ``get_db()`` and then
    ``await start_tweet_stream()`` - and the ``shutdown`` handler at line 35 stay
    registered and never run.  Each client is nevertheless ``close()``d on
    teardown, which releases its ``httpx`` transport without invoking either
    handler.
Transport
    Requests travel over starlette's in-process ASGI transport, so serving a
    request opens no socket.
Dependency injection
    Data reaches a handler through :func:`override_get_db`, which keys
    ``app.dependency_overrides`` on ``app.db.firestore.get_db`` by object
    identity.
Isolation
    Every fixture here is function-scoped, so this layer's suites impose no
    ordering requirement on one another.  The one shared object - the application
    built at ``app/main.py`` module scope, which is never re-imported - carries
    the ``dependency_overrides`` map, and :func:`reset_dependency_overrides`
    empties it before and after every test regardless of which fixtures that test
    named.

Fixtures
--------
:func:`main_module`
    The imported ``app.main`` module.
:func:`integration_app`
    The ``FastAPI`` instance that module built at import.
:func:`reset_dependency_overrides`
    Autouse. Empties the shared override map on entry and on exit.
:func:`client`
    ``TestClient`` that re-raises an exception raised inside a handler, closed on
    teardown.
:func:`client_no_raise`
    ``TestClient`` that reports one as a ``500`` response instead, closed on
    teardown.
:func:`mock_db`
    Unprogrammed stand-in for the object ``Depends(get_db)`` yields.
:func:`override_get_db`
    Installs a stand-in and empties the override map on teardown.

Everything shared with the unit layer is consumed from the parent
``backend/tests/conftest.py`` and is not restated here: the five shims for
symbols production code imports but never defines (``Optional``, ``LLMService``,
``add_response``, ``verify_token`` and ``TwitterService``), the seeded and pinned
``Settings`` environment variables, the autouse credential neutraliser and the
autouse network guard.  This module installs no shim, seeds no environment
variable and defines no fixture whose name would shadow one of the parent's.

Reasoning for the client lifecycle and the override contract:
``docs/testing/DECISION-LOG.md`` row D107.
"""

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

    Builds no second application and re-runs neither wiring function.
    """
    return main_module.app


# HTTP clients.  Neither is entered as a context manager, so no lifecycle
# handler runs; see the Lifecycle note in the module docstring.  Each is closed
# from a ``finally`` block, so a test that fails mid-request still releases its
# transport, and ``close()`` is the counterpart of construction rather than of
# ``__enter__``, so it invokes no handler either.


@pytest.fixture
def client(integration_app):
    """Yield a ``TestClient`` that re-raises exceptions from a handler.

    ``raise_server_exceptions`` keeps its default of ``True``, so an exception
    raised inside a handler propagates out of the request call instead of being
    reported as a response, which is what lets a test name the exception type
    with ``pytest.raises``.
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
    with ``status_code == 500`` rather than propagating.
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

    Each tweets handler drives a different call chain off the injected object, so
    a test programs only the attributes the endpoint under test reaches.  Pass it
    to :func:`override_get_db` to install it.
    """
    return MagicMock(name="mock_db")


@pytest.fixture(autouse=True)
def reset_dependency_overrides(integration_app):
    """Empty ``app.dependency_overrides`` before and after every test here.

    Autouse and unconditional, so the guarantee does not depend on which fixtures
    a test happens to name: a test that installs an override directly on
    ``integration_app.dependency_overrides``, or that fails part way through doing
    so, cannot leave an entry behind.  Clearing on entry as well as on exit makes
    the order tests execute in irrelevant.

    Requests :func:`integration_app` rather than importing ``app.main`` itself,
    because that module cannot be imported without the three shims the parent
    conftest's ``app_module`` fixture installs.

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

    Teardown clears the map unconditionally.  Not autouse, so a test needing no
    injected database simply does not request it.
    """

    def _override_get_db(db):
        integration_app.dependency_overrides[firestore.get_db] = lambda: db
        return db

    try:
        yield _override_get_db
    finally:
        integration_app.dependency_overrides.clear()

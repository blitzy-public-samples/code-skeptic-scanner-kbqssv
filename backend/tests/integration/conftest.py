"""Fixtures for the integration layer of the Code Skeptic Scanner backend.

This module is the only place the suites in ``backend/tests/integration`` reach
production code from. It turns the already-wired ``app.main.app`` object into a
per-test HTTP client and owns the ``app.dependency_overrides`` contract,
including the teardown that empties the override map after every test.

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
    blocks on a live Twitter stream.
Transport
    Requests travel over starlette's in-process ASGI transport, so serving a
    request opens no socket.
Dependency injection
    Data reaches a handler through :func:`override_get_db`, which keys
    ``app.dependency_overrides`` on ``app.db.firestore.get_db``.
Isolation
    Every fixture here is function-scoped, so no client, application override
    or stand-in is shared between tests and this layer's suites impose no
    ordering requirement on one another.

Fixtures
--------
:func:`main_module`
    The imported ``app.main`` module.
:func:`integration_app`
    The ``FastAPI`` instance that module built at import.
:func:`client`
    ``TestClient`` that re-raises an exception raised inside a handler.
:func:`client_no_raise`
    ``TestClient`` that reports one as a ``500`` response instead.
:func:`mock_db`
    Unprogrammed stand-in for the object ``Depends(get_db)`` yields.
:func:`override_get_db`
    Installs a stand-in and empties the override map on teardown.

Everything shared with the unit layer is consumed from the parent
``backend/tests/conftest.py`` and is not restated here: the five shims for
symbols production code imports but never defines (``Optional``,
``LLMService``, ``add_response``, ``verify_token`` and ``TwitterService``), the
eight seeded ``Settings`` environment variables, the autouse credential
neutraliser and the autouse network guard. This module installs no shim, seeds
no environment variable and defines no fixture whose name would shadow one of
the parent's.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.db.firestore as firestore

# --------------------------------------------------------------------------- #
# Application object.
# --------------------------------------------------------------------------- #


@pytest.fixture
def main_module(app_module):
    """Return the imported ``app.main`` module.

    ``app_module`` is the parent conftest's fixture. It installs the
    ``verify_token``, ``TwitterService`` and ``LLMService`` shims that
    ``app.main``'s import graph needs in order to load at all, and yields the
    module object itself, so this fixture forwards that object unchanged. The
    shims stay installed for the duration of the test.

    The lifecycle suite patches against this module object.
    ``main_module.start_tweet_stream`` and ``main_module.get_db`` are the names
    ``app/main.py`` lines 5 and 6 bind into its own namespace, and that
    namespace is the boundary a patch has to target for the handlers registered
    in the module to observe it. ``main_module.settings`` is the ``Settings``
    instance built at line 9.
    """
    return app_module


@pytest.fixture
def integration_app(main_module):
    """Return the ``FastAPI`` instance ``app.main`` built at import.

    ``app/main.py`` line 8 constructs it with no keyword arguments and lines 41
    and 42 run ``configure_cors(app)`` and ``include_routers(app)``, so it
    arrives carrying one ``CORSMiddleware`` entry and one copy of each of the
    four routers. This fixture constructs no second application and re-runs
    neither wiring function.

    Only ``app/api/routes/tweets.py`` contributes endpoints — ``GET /tweets``,
    ``GET /tweets/{tweet_id}`` and ``POST /tweets/{tweet_id}/responses``.
    ``users.py``, ``analytics.py`` and ``config.py`` each expose a bare
    ``APIRouter()``, and no route carries the ``API_V1_STR`` prefix.
    """
    return main_module.app


# --------------------------------------------------------------------------- #
# HTTP clients.  Neither is entered as a context manager, so no lifecycle
# handler runs; see the module docstring.
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(integration_app):
    """Return a ``TestClient`` that re-raises exceptions from a handler.

    The client is constructed and returned, never entered as a context
    manager, so the ``startup`` and ``shutdown`` handlers stay registered but
    uninvoked.

    ``raise_server_exceptions`` keeps its default of ``True``, so an exception
    raised inside a handler propagates out of the request call instead of being
    reported as a response. That is what lets a test name the exception type
    with ``pytest.raises``.
    """
    return TestClient(integration_app)


@pytest.fixture
def client_no_raise(integration_app):
    """Return a ``TestClient`` that reports a handler exception as a ``500``.

    Identical to :func:`client` apart from ``raise_server_exceptions=False``,
    which makes an unhandled exception inside a handler surface as a response
    with ``status_code == 500`` rather than propagating. This client is
    likewise never entered as a context manager, so no lifecycle handler runs.
    """
    return TestClient(integration_app, raise_server_exceptions=False)


# --------------------------------------------------------------------------- #
# Dependency injection.
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_db():
    """Return an unprogrammed ``MagicMock`` standing in for the database.

    ``app/api/routes/tweets.py`` puts ``Depends(get_db)`` in all three handler
    signatures and each handler drives a different call chain off the injected
    object, so no chain is programmed here. A test programs only the attributes
    the endpoint under test reaches — for ``GET /tweets`` that is
    ``mock_db.query.return_value.offset.return_value.limit.return_value.all``
    — and leaves the rest of the surface untouched.

    Pass it to :func:`override_get_db` to install it.
    """
    return MagicMock(name="mock_db")


@pytest.fixture
def override_get_db(integration_app):
    """Yield a callable that injects an object in place of ``get_db``.

    Call it with the object the handlers should receive::

        def test_lists_tweets(client, mock_db, override_get_db):
            override_get_db(mock_db)
            response = client.get("/tweets")

    The callable sets
    ``integration_app.dependency_overrides[app.db.firestore.get_db]`` to a
    zero-argument callable returning ``db``, then returns ``db`` so the
    injected object can be bound in the same statement.

    ``dependency_overrides`` is matched by object identity against the function
    that ``app/api/routes/tweets.py`` captured in its three ``Depends(get_db)``
    defaults when it was imported. The parent conftest imports that router
    while ``app.db.firestore.get_db`` is still the real function and leaves the
    module cached for the rest of the session, so the ``firestore.get_db`` read
    here is that same object and the override matches.

    Teardown runs ``integration_app.dependency_overrides.clear()``. The
    application object outlives every test, so the map is emptied
    unconditionally — whether this fixture installed an override, the test
    installed one itself, the test installed none, or the test failed before
    reaching its assertions.

    This fixture is not autouse. A test needing no injected database — the
    route-surface census, whose requests are answered by starlette's 404
    handler and reach no endpoint — simply does not request it, and a test that
    does request it observes an empty override map on entry.
    """

    def _override_get_db(db):
        integration_app.dependency_overrides[firestore.get_db] = lambda: db
        return db

    try:
        yield _override_get_db
    finally:
        integration_app.dependency_overrides.clear()

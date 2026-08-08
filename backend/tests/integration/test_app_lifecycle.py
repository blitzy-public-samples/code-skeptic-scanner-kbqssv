"""Integration suite for ``app/main.py``, which assembles the application.

Subject
-------
``app/main.py`` is forty-two lines and builds the entire application at its
own module scope.  Line 8 constructs ``app = FastAPI()`` with no keyword
arguments; line 9 constructs a second, independent ``Settings()``; lines
11-18 define the CORS wiring function and lines 20-24 the router wiring
function; lines 26-33 and 35-39 register the ``startup`` and ``shutdown``
handlers; lines 41 and 42 invoke both wiring functions.  Every one of those
statements has therefore already run by the time any test here observes the
application.

What this suite asserts
-----------------------
CORS configuration
    ``settings.ALLOWED_ORIGINS`` is the empty list; the ``CORSMiddleware``
    entry on ``user_middleware`` carries exactly the four options lines 14 to
    17 pass and nothing else; that entry appears exactly once.  At request
    level a response to an arbitrary ``Origin`` carries no
    ``access-control-allow-origin`` header, and a preflight for one is
    answered ``400`` with the body ``Disallowed CORS origin``.
Router wiring
    The four route modules line 3 imports are the four modules this
    application wired.  Only ``app/api/routes/tweets.py`` contributes
    endpoints - three of them - and the application's own operations are
    exactly those three, every path under ``/tweets``.  The route table is
    already populated without this suite invoking either wiring function.
Lifecycle registration
    ``startup_event`` and ``shutdown_event`` are the sole entries on the
    application router's startup and shutdown handler lists, and neither body
    runs: serving a request and then closing the client leave ``get_db`` and
    ``start_tweet_stream`` - the two names ``app/main.py`` lines 5 and 6 bind
    into its own namespace - at a call count of zero.
Application object
    ``PROJECT_NAME`` never reaches the application object.

Current behaviour captured as divergence
----------------------------------------
* ``settings.PROJECT_NAME`` is ``"Twitter Bot"`` while ``app.title`` is
  ``"FastAPI"``, the framework's own default: line 8 passes no ``title``, so
  the project name is unobservable on the application and absent from the
  generated OpenAPI document.
* ``ALLOWED_ORIGINS`` carries the empty list rather than ``["*"]``, so the
  application as configured answers no cross-origin request at all.  A simple
  response nevertheless carries ``access-control-allow-credentials: true``,
  because line 15 passes ``allow_credentials=True`` and starlette emits that
  header independently of whether the origin was allowed.
* Line 9 builds a ``Settings`` instance of its own.  It is a different object
  from ``app.core.config.settings``, so the application reads its
  configuration from a second snapshot of the environment.
* ``include_router`` is called four times, at lines 21 to 24, and three of the
  four routers are bare, so three of those calls contribute nothing.
* No route carries the ``/api/v1`` prefix that ``Settings.API_V1_STR``
  declares.
* The ``startup`` and ``shutdown`` bodies are executed by no test, so
  ``app/main.py`` stays short of full line coverage by design.  The module is
  outside the coverage gate, which covers ``app/core``, ``app/services``,
  ``app/tasks`` and ``app/db``.

Scope
-----
The wiring facts specific to ``app/main.py``.  The exhaustive route table and
the 404 census for the unimplemented ``/users``, ``/analytics`` and
``/config`` surfaces belong to ``tests/integration/test_route_surface.py``;
the behaviour of the three implemented endpoints belongs to
``tests/integration/test_http_tweets.py``.

Every request below is served over the in-process ASGI transport and is
answered either by a built-in route or by the CORS middleware, so no test
here needs a database, none installs a dependency override and none opens a
socket.  No client is entered as a context manager, which is the mechanism
that leaves both lifecycle handlers registered and unrun.

Reasoning for the client lifecycle these assertions rest on:
``docs/testing/DECISION-LOG.md`` rows D28 and D107.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# Oracles.  Every value below was read from the running application on the
# pinned stack - fastapi 0.95.2, starlette 0.27.0, pydantic 1.10.13.
# --------------------------------------------------------------------------- #

#: ``Settings.ALLOWED_ORIGINS``, declared ``List[str] = []`` at
#: ``app/core/config.py`` line 22 and read by ``app/main.py`` line 14.
EXPECTED_ALLOWED_ORIGINS = []

#: ``allow_methods`` from ``app/main.py`` line 16.
EXPECTED_ALLOW_METHODS = ["*"]

#: ``allow_headers`` from ``app/main.py`` line 17.
EXPECTED_ALLOW_HEADERS = ["*"]

#: Every keyword ``app/main.py`` lines 14 to 17 pass to ``add_middleware``,
#: sorted.  Asserted as a complete set: these four and no others.
EXPECTED_CORS_OPTION_NAMES = (
    "allow_credentials",
    "allow_headers",
    "allow_methods",
    "allow_origins",
)

#: ``Settings.PROJECT_NAME``'s declared default.  ``backend/tests/conftest.py``
#: pins it into the environment, which fixes the value every settings singleton
#: in the suite reports.
EXPECTED_PROJECT_NAME = "Twitter Bot"

#: ``FastAPI()``'s own default ``title``.  ``app/main.py`` line 8 passes no
#: keyword arguments, so this is what the application carries.
DEFAULT_FASTAPI_TITLE = "FastAPI"

#: Number of routes on ``app/api/routes/tweets.py``'s router: the two ``GET``
#: endpoints at lines 11 and 16 and the ``POST`` endpoint at line 23.
TWEETS_ROUTER_ROUTE_COUNT = 3

#: Handlers registered by ``app/main.py`` lines 26 and 35, in registration
#: order, identified by ``__name__``.
EXPECTED_STARTUP_HANDLER_NAMES = ["startup_event"]
EXPECTED_SHUTDOWN_HANDLER_NAMES = ["shutdown_event"]

#: Prefix shared by every path the application serves from its own routers.
TWEETS_PATH = "/tweets"

#: Built-in route ``FastAPI`` generates for itself.  It reaches no router
#: endpoint, so a request for it resolves no ``Depends(get_db)``, touches no
#: database and returns :data:`HTTP_OK`.
OPENAPI_PATH = "/openapi.json"

#: Origin used for the two CORS request-level assertions.  Never resolved: the
#: egress guard in ``backend/tests/conftest.py`` stays armed throughout, and
#: the CORS middleware rejects the value without contacting the host.
ARBITRARY_ORIGIN = "http://arbitrary.example"

HTTP_OK = 200

#: starlette 0.27.0 answers a preflight naming an origin outside the allow-list
#: with this status and this plain-text body.
DISALLOWED_PREFLIGHT_STATUS = 400
DISALLOWED_PREFLIGHT_BODY = "Disallowed CORS origin"

#: Response header names, lower-cased because ``httpx`` compares them
#: case-insensitively but reads them back lower-cased.
ACCESS_CONTROL_ALLOW_ORIGIN = "access-control-allow-origin"
ACCESS_CONTROL_ALLOW_CREDENTIALS = "access-control-allow-credentials"


# --------------------------------------------------------------------------- #
# Helpers.  Both read the application and mutate nothing.
# --------------------------------------------------------------------------- #


def _cors_middleware_entries(application):
    """Return the ``user_middleware`` entries whose ``cls`` is the CORS class.

    On starlette 0.27.0 an entry exposes exactly two attributes, ``cls`` and
    ``options``, the latter a ``dict`` of the keyword arguments
    ``add_middleware`` received.
    """
    return [
        entry
        for entry in application.user_middleware
        if entry.cls is CORSMiddleware
    ]


def _application_operations(application):
    """Return the application's own operations, in route-table order.

    ``application.routes`` also holds the four ``starlette.routing.Route``
    entries ``FastAPI`` generates for ``/openapi.json``, ``/docs``,
    ``/docs/oauth2-redirect`` and ``/redoc``.  Only an endpoint contributed by
    an ``APIRouter`` is an ``APIRoute``, so the type test is what separates the
    application's own surface from the framework's.
    """
    return [
        route for route in application.routes if isinstance(route, APIRoute)
    ]


# --------------------------------------------------------------------------- #
# CORS configuration - ``app/main.py`` lines 11-18, invoked at line 41.
# --------------------------------------------------------------------------- #


def test_configure_cors_uses_empty_allowed_origins(main_module):
    """The settings instance the CORS wiring reads carries the empty list.

    ``app/main.py`` line 14 reads ``settings.ALLOWED_ORIGINS`` off the instance
    line 9 built.  ``app/core/config.py`` line 22 declares the field
    ``List[str] = []``, the least permissive value, not ``["*"]``.
    """
    assert main_module.settings.ALLOWED_ORIGINS == EXPECTED_ALLOWED_ORIGINS


def test_cors_middleware_registered_with_expected_options(integration_app):
    """The registered CORS middleware carries exactly the declared options.

    Asserts the value of each keyword ``app/main.py`` lines 14 to 17 pass, and
    then that those four are the only keywords the entry holds.
    """
    cors_entries = _cors_middleware_entries(integration_app)
    assert len(cors_entries) == 1

    options = cors_entries[0].options
    assert options["allow_origins"] == EXPECTED_ALLOWED_ORIGINS
    assert options["allow_credentials"] is True
    assert options["allow_methods"] == EXPECTED_ALLOW_METHODS
    assert options["allow_headers"] == EXPECTED_ALLOW_HEADERS
    assert tuple(sorted(options)) == EXPECTED_CORS_OPTION_NAMES


def test_cors_middleware_registered_exactly_once(integration_app):
    """``CORSMiddleware`` appears once on the application's middleware list.

    The application object is built once, at ``app/main.py`` line 8, and wired
    once, at line 41.  A second registration would mean either that the module
    was re-imported or that a test invoked the wiring function itself; both
    would show up here as a second entry.
    """
    assert len(_cors_middleware_entries(integration_app)) == 1


def test_cors_headers_absent_for_arbitrary_origin(client):
    """A response to an arbitrary ``Origin`` withholds the allow-origin header.

    The request-level consequence of the empty allow-list.  The middleware does
    run - it emits ``access-control-allow-credentials`` because
    ``app/main.py`` line 15 passes ``allow_credentials=True`` - and still
    declines to name the origin, which distinguishes an origin that was refused
    from a middleware that was never in the stack.
    """
    response = client.get(OPENAPI_PATH, headers={"Origin": ARBITRARY_ORIGIN})

    assert response.status_code == HTTP_OK
    assert ACCESS_CONTROL_ALLOW_ORIGIN not in response.headers
    assert response.headers[ACCESS_CONTROL_ALLOW_CREDENTIALS] == "true"


def test_cors_preflight_rejects_arbitrary_origin(client):
    """A preflight naming an arbitrary origin is refused with ``400``.

    starlette 0.27.0 answers a preflight whose ``Origin`` is outside the
    allow-list with the status and plain-text body asserted here, and names no
    allowed origin in the response.
    """
    response = client.options(
        TWEETS_PATH,
        headers={
            "Origin": ARBITRARY_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == DISALLOWED_PREFLIGHT_STATUS
    assert response.text == DISALLOWED_PREFLIGHT_BODY
    assert ACCESS_CONTROL_ALLOW_ORIGIN not in response.headers


# --------------------------------------------------------------------------- #
# Router wiring - ``app/main.py`` lines 20-24, invoked at line 42.
#
# The four route modules are imported inside each test body rather than at
# this module's scope.  ``app/api/routes/tweets.py`` line 6 imports
# ``TwitterService`` from ``app.services.twitter_service``, which defines no
# such name, so the import resolves only while the fail-closed shims are
# installed - which is for the duration of a test, by the ``app_module``
# fixture in ``backend/tests/conftest.py``.  A module-scope import would raise
# ``ImportError`` during collection.  Every test in this directory reaches
# that fixture, because the autouse ``reset_dependency_overrides`` fixture in
# ``tests/integration/conftest.py`` requests it transitively.
# --------------------------------------------------------------------------- #


def test_include_routers_is_called_for_four_routers_only_one_of_which_contributes_routes(
    integration_app, main_module
):
    """Four routers are wired; only the tweets router carries any endpoint.

    ``app/main.py`` lines 21 to 24 call ``include_router`` four times.  Three
    of the four routers are a bare ``APIRouter()``, so the application's whole
    surface comes from the fourth: three operations, every path under
    ``/tweets``.

    ``app.api.routes.config`` is aliased on import because ``app.core.config``
    shares its trailing name.
    """
    from app.api.routes import analytics as analytics_routes
    from app.api.routes import config as config_routes
    from app.api.routes import tweets as tweets_routes
    from app.api.routes import users as users_routes

    # The four modules ``app/main.py`` line 3 bound are these four.
    assert (
        main_module.tweets,
        main_module.users,
        main_module.analytics,
        main_module.config,
    ) == (tweets_routes, users_routes, analytics_routes, config_routes)

    assert len(tweets_routes.router.routes) == TWEETS_ROUTER_ROUTE_COUNT
    assert users_routes.router.routes == []
    assert analytics_routes.router.routes == []
    assert config_routes.router.routes == []

    operations = _application_operations(integration_app)
    assert len(operations) == TWEETS_ROUTER_ROUTE_COUNT

    paths_outside_tweets = [
        route.path
        for route in operations
        if not route.path.startswith(TWEETS_PATH)
    ]
    assert paths_outside_tweets == []


def test_routers_are_wired_at_import_time(integration_app):
    """The route table already holds the tweets endpoints before any test acts.

    ``app/main.py`` line 42 runs at import, so the application arrives wired.
    This test invokes neither wiring function and installs nothing, yet the
    application's operations already carry, in order, the three endpoint
    functions the tweets router declares.  ``include_router`` builds a fresh
    ``APIRoute`` per endpoint, so the route objects differ while the endpoint
    functions are the same objects.
    """
    from app.api.routes import tweets as tweets_routes

    operations = _application_operations(integration_app)
    declared_routes = tweets_routes.router.routes
    wired_endpoints = [route.endpoint for route in operations]
    declared_endpoints = [route.endpoint for route in declared_routes]

    assert wired_endpoints == declared_endpoints
    assert len(wired_endpoints) == TWEETS_ROUTER_ROUTE_COUNT


# --------------------------------------------------------------------------- #
# Lifecycle - ``app/main.py`` lines 26-33 and 35-39: registered, never invoked.
#
# The startup handler calls ``get_db()`` and then awaits
# ``start_tweet_stream()``, which blocks on a live Twitter stream; the shutdown
# handler calls ``get_db()``.  Both are asserted by registration and by call
# count, never by execution.  The two patches target the names ``app/main.py``
# lines 5 and 6 bound into its own namespace, which is what the handler bodies
# resolve at call time.
# --------------------------------------------------------------------------- #


def test_startup_and_shutdown_handlers_are_registered(integration_app):
    """``startup_event`` and ``shutdown_event`` are the sole entries.

    ``app/main.py`` lines 26 and 35 decorate one handler each, so each list on
    the application router holds exactly one entry.  Identified by ``__name__``
    so the oracle names the production function rather than merely counting.
    """
    application_router = integration_app.router
    startup_handler_names = [
        handler.__name__ for handler in application_router.on_startup
    ]
    shutdown_handler_names = [
        handler.__name__ for handler in application_router.on_shutdown
    ]

    assert startup_handler_names == EXPECTED_STARTUP_HANDLER_NAMES
    assert shutdown_handler_names == EXPECTED_SHUTDOWN_HANDLER_NAMES


def test_startup_handler_is_not_invoked_by_the_test_client(
    client, main_module
):
    """Serving a request runs neither statement of the startup handler.

    The client is never entered as a context manager, so starlette runs no
    lifespan and the handler registered at ``app/main.py`` line 26 stays
    dormant.  Both names its body would reach - ``get_db`` at line 31 and
    ``start_tweet_stream`` at line 33 - are replaced for the duration of a
    served request and finish at a call count of zero.  The status assertion is
    what makes the two call counts meaningful: the request really was served.
    """
    mock_get_db = MagicMock(name="mock_get_db")
    mock_start_tweet_stream = MagicMock(name="mock_start_tweet_stream")

    with patch.object(main_module, "get_db", mock_get_db), patch.object(
        main_module, "start_tweet_stream", mock_start_tweet_stream
    ):
        response = client.get(OPENAPI_PATH)

    assert response.status_code == HTTP_OK
    assert mock_get_db.call_count == 0
    assert mock_start_tweet_stream.call_count == 0


def test_shutdown_handler_is_not_invoked_by_the_test_client(
    client, main_module
):
    """Closing the client runs neither statement of the shutdown handler.

    ``close()`` is the counterpart of construction, not of ``__enter__``, so
    releasing the transport does not trigger the handler registered at
    ``app/main.py`` line 35.  ``get_db``, which its body reaches at line 37,
    is replaced across a served request and the close that follows it, and
    finishes at a call count of zero.  Closing again on fixture teardown is a
    no-op.
    """
    mock_get_db = MagicMock(name="mock_get_db")

    with patch.object(main_module, "get_db", mock_get_db):
        response = client.get(OPENAPI_PATH)
        client.close()

    assert response.status_code == HTTP_OK
    assert mock_get_db.call_count == 0


# --------------------------------------------------------------------------- #
# The application object - ``app/main.py`` line 8.
# --------------------------------------------------------------------------- #


def test_app_is_constructed_without_project_name(integration_app, main_module):
    """``PROJECT_NAME`` is configured and never reaches the application.

    Captures the divergence directly: ``Settings`` declares
    ``PROJECT_NAME = "Twitter Bot"`` and the application carries ``FastAPI``'s
    own default title, because line 8 constructs ``FastAPI()`` with no keyword
    arguments and no later statement assigns a title.
    """
    assert main_module.settings.PROJECT_NAME == EXPECTED_PROJECT_NAME
    assert integration_app.title == DEFAULT_FASTAPI_TITLE

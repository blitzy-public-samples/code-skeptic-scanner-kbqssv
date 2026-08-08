"""Integration suite for the route surface of ``app.main.app``.

Subject
-------
``app/main.py`` line 3 imports four route modules from ``app.api.routes`` and
``include_routers`` at lines 20-24 includes all four routers.  Only
``app/api/routes/tweets.py`` declares endpoints -- three of them.  ``users.py``,
``analytics.py`` and ``config.py`` each declare a bare ``APIRouter()`` and no
endpoint.  No ``include_router`` call passes a ``prefix``, and
``Settings.API_V1_STR`` -- declared ``"/api/v1"`` at ``app/core/config.py``
line 6 -- reaches no route.

What this suite asserts
-----------------------
The 404 census
    Nine ``(method, path)`` operations answer ``404``: the three legacy
    ``/users`` operations, the two legacy ``/analytics`` operations, the two
    legacy ``/config`` operations, ``GET /health`` and ``POST /token``.
    Each is a separately reported parametrised case.
That a census 404 came from the router
    The body of an unrouted request is exactly ``{"detail": "Not Found"}``.
    ``app/api/routes/tweets.py`` line 20 raises
    ``HTTPException(404, "Tweet not found")``, so a status code alone does not
    distinguish an absent route from a handler rejecting a present one; the body
    does.
The two legacy paths that are not 404
    ``DELETE /tweets/1`` answers ``405`` with ``allow: GET`` and the body
    ``{"detail": "Method Not Allowed"}`` -- the path matches
    ``/tweets/{tweet_id}`` and the method does not.  ``POST /tweets/`` answers
    ``307`` to the collection path when redirects are not followed, and ``405``
    once followed, because ``app.router.redirect_slashes`` is at its default.
The declared method sets
    The three application operations declare ``{"GET"}``, ``{"GET"}`` and
    ``{"POST"}``.  The four routes FastAPI adds for its own documentation
    declare ``{"GET", "HEAD"}``.
The HEAD consequence of those method sets
    ``HEAD /tweets`` answers ``405`` with ``allow: GET``; ``HEAD /docs``
    answers ``200``.
No ``API_V1_STR`` prefixing
    ``API_V1_STR`` is declared ``"/api/v1"``; no route path starts with it; and
    a request to that prefix joined to the collection path answers ``404``.
The exact route table
    Seven paths, by set equality: the three ``/tweets`` paths plus
    ``/openapi.json``, ``/docs``, ``/docs/oauth2-redirect`` and ``/redoc``.
    Exactly three of the seven are the application's own operations, and the
    published OpenAPI document names exactly those three -- ``get``, ``get``
    and ``post``.
The bare routers, structurally
    ``users.router.routes``, ``analytics.router.routes`` and
    ``config.router.routes`` are each empty, while ``tweets.router`` carries
    three routes.  This is the module-level counterpart of the request-level
    census.

Current behaviour captured as divergence
----------------------------------------
``fastapi.routing.APIRoute`` does not synthesise ``HEAD`` from ``GET``, while
the ``starlette.routing.Route`` it derives from does.  Measured on the pinned
stack -- fastapi 0.95.2 over starlette 0.27.0 -- the four documentation routes
are plain ``Route`` objects reporting ``{"GET", "HEAD"}`` and serving
``HEAD /docs`` with ``200``, while the three ``APIRoute`` objects report GET,
GET and POST and answer ``HEAD /tweets`` with ``405``.  Both halves are
asserted, structurally and at the request level.

``Settings.API_V1_STR`` is declared and read by nothing: the constant exists and
prefixes no route.

``app/api/dependencies.py`` line 6 declares
``OAuth2PasswordBearer(tokenUrl="token")``, and no ``/token`` route exists on any
router.

``infrastructure/docker/docker-compose.yml`` and ``.github/workflows/cd.yml``
both probe a ``/health`` route.  No router declares one, so the probe target
answers ``404``.

No implemented endpoint accepts a request body, so no route on this application
can produce a ``422``.

``FastAPI()`` is constructed at ``app/main.py`` line 8 with no keyword
arguments, so the published document carries the framework defaults -- title
``"FastAPI"``, version ``"0.1.0"`` -- and the four documentation routes are
present with ``include_in_schema`` false.

The legacy route census
-----------------------
``backend/tests/test_api.py`` asserted ten distinct operations.  Nine are
covered here; the tenth is implemented and belongs to the suite that exercises
it.

===================================  ==========================================
Legacy operation                     Where its real behaviour is asserted
===================================  ==========================================
``POST /tweets/``                    ``test_trailing_slash_on_tweets_...``
``GET /tweets/1``                    ``tests/integration/test_http_tweets.py``
``DELETE /tweets/1``                 ``test_implemented_path_rejects_...``
``POST /users/``                     census ``post-users-collection``
``GET /users/1``                     census ``get-users-by-id``
``PUT /users/1``                     census ``put-users-by-id``
``GET /analytics/tweets``            census ``get-analytics-tweets``
``GET /analytics/users``             census ``get-analytics-users``
``GET /config``                      census ``get-config``
``PUT /config``                      census ``put-config``
===================================  ==========================================

Of the three operations this application implements, exactly one --
``GET /tweets/{tweet_id}`` -- is among the legacy ten.

Scope
-----
Every request here is expected to be refused by the router, so none reaches a
handler and no dependency override is installed: ``app.dependency_overrides``
stays as the autouse fixture in ``backend/tests/integration/conftest.py`` leaves
it.  This module installs no mock, no patch and no import shim, and constructs
no client of its own.

Not covered here, and covered elsewhere:

* the behaviour of the three implemented ``/tweets`` operations --
  ``tests/integration/test_http_tweets.py``;
* CORS configuration, router inclusion and lifecycle-handler registration --
  ``tests/integration/test_app_lifecycle.py``;
* the aggregation intent behind ``/analytics/tweets`` and ``/analytics/users``
  -- ``tests/unit/test_services_analytics.py``, at the layer that implements it;
* the two ``401`` paths that do exist -- ``tests/unit/test_api_dependencies.py``,
  which calls ``get_current_user`` directly;
* the declared values of ``Settings`` fields -- ``tests/unit/test_core_config.py``.

Reasoning for the authorized production touches this surface rests on, and for
the disposition of the legacy assertions: ``docs/testing/DECISION-LOG.md`` rows
D50, D52, D53, D60 and D62.  ``docs/testing/TRACEABILITY-MATRIX.md`` section E.1
rows E4-E10 and section E.2 record which legacy function each census case
absorbs; the census ids below are the handles it cites.
"""

import pytest
from fastapi.routing import APIRoute

import app.core.config as config_module

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# Oracles.  Every value below was read from the running application on the
# pinned stack; none is inferred from the design documents.
# --------------------------------------------------------------------------- #

NOT_FOUND_STATUS = 404

METHOD_NOT_ALLOWED_STATUS = 405

TEMPORARY_REDIRECT_STATUS = 307

OK_STATUS = 200

#: Body starlette's router returns when no route matches.  Distinct from the
#: ``{"detail": "Tweet not found"}`` a tweets handler raises.
ROUTER_NOT_FOUND_BODY = {"detail": "Not Found"}

#: Body starlette's router returns when a path matches and the method does not.
ROUTER_METHOD_NOT_ALLOWED_BODY = {"detail": "Method Not Allowed"}

#: Value ``app/core/config.py`` line 6 declares for ``API_V1_STR``.  The single
#: literal for it in this module: the two tests that probe for prefixing read
#: the field itself, so the constant and the application cannot drift apart.
API_V1_STR_DECLARED = "/api/v1"

# Route paths as ``app/api/routes/tweets.py`` declares them.

TWEETS_COLLECTION_PATH = "/tweets"

TWEET_DETAIL_PATH = "/tweets/{tweet_id}"

TWEET_RESPONSES_PATH = "/tweets/{tweet_id}/responses"

IMPLEMENTED_PATHS = (
    TWEETS_COLLECTION_PATH,
    TWEET_DETAIL_PATH,
    TWEET_RESPONSES_PATH,
)

#: Paths FastAPI adds for its own documentation.  Each is a plain
#: ``starlette.routing.Route`` rather than an ``APIRoute``, and each carries
#: ``include_in_schema`` false, which is why none appears in the published
#: document.
FASTAPI_BUILTIN_PATHS = (
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
)

#: The whole route table, as a set.  Asserted by equality, so a path added
#: anywhere fails the assertion.
EXPECTED_ROUTE_PATHS = frozenset(IMPLEMENTED_PATHS + FASTAPI_BUILTIN_PATHS)

#: Operations the application itself declares -- three, against the ten the
#: legacy suite asserted.
IMPLEMENTED_OPERATION_COUNT = 3

#: HTTP methods each ``APIRoute`` declares.  ``HEAD`` is absent from both GET
#: entries; see the divergence note in the module docstring.
EXPECTED_METHODS_BY_PATH = {
    TWEETS_COLLECTION_PATH: frozenset({"GET"}),
    TWEET_DETAIL_PATH: frozenset({"GET"}),
    TWEET_RESPONSES_PATH: frozenset({"POST"}),
}

#: Methods every documentation route declares.
BUILTIN_METHODS = frozenset({"GET", "HEAD"})

#: ``paths`` of ``app.openapi()``, lower-cased operation names per path.
EXPECTED_OPENAPI_OPERATIONS = {
    TWEETS_COLLECTION_PATH: frozenset({"get"}),
    TWEET_DETAIL_PATH: frozenset({"get"}),
    TWEET_RESPONSES_PATH: frozenset({"post"}),
}

#: ``allow`` header on a refusal at either ``/tweets`` or ``/tweets/{tweet_id}``:
#: the only method those routes declare.
EXPECTED_ALLOW_HEADER = "GET"

# Concrete request targets.  A path parameter is filled in with the same value
# the legacy suite used, so a census case and its antecedent name one URL.

#: Concrete form of :data:`TWEET_DETAIL_PATH`, as ``test_delete_tweet`` wrote it.
TWEET_DETAIL_REQUEST_PATH = "/tweets/1"

#: Collection path with the trailing slash ``test_create_tweet`` wrote.
TWEETS_COLLECTION_TRAILING_SLASH_PATH = "/tweets/"

#: Unrouted path used where one representative absent target is enough.
UNROUTED_SAMPLE_PATH = "/users/1"

#: Documentation route probed for the ``HEAD`` contrast.
SWAGGER_UI_PATH = "/docs"

#: Route modules ``app/main.py`` line 3 imports whose routers carry no endpoint.
BARE_ROUTER_MODULE_NAMES = ("users", "analytics", "config")

#: Routes ``app/api/routes/tweets.py`` registers on its router.
TWEETS_ROUTER_ROUTE_COUNT = 3

#: The census.  Every id is stable and names the operation rather than its
#: position, so the traceability matrix can cite one case and a ``-k``
#: expression can select one.  The first seven are the operations the legacy
#: suite asserted against routers that declare no endpoint; the last two record
#: absences the repository refers to elsewhere -- a ``/health`` probe in
#: ``docker-compose.yml`` and ``cd.yml``, and the ``tokenUrl="token"`` on
#: ``app/api/dependencies.py`` line 6.
ABSENT_OPERATIONS = (
    pytest.param("POST", "/users/", id="post-users-collection"),
    pytest.param("GET", "/users/1", id="get-users-by-id"),
    pytest.param("PUT", "/users/1", id="put-users-by-id"),
    pytest.param("GET", "/analytics/tweets", id="get-analytics-tweets"),
    pytest.param("GET", "/analytics/users", id="get-analytics-users"),
    pytest.param("GET", "/config", id="get-config"),
    pytest.param("PUT", "/config", id="put-config"),
    pytest.param("GET", "/health", id="get-health"),
    pytest.param("POST", "/token", id="post-token"),
)


# --------------------------------------------------------------------------- #
# Helpers and the one fixture specific to this module.  Everything else comes
# from backend/tests/integration/conftest.py and backend/tests/conftest.py.
# --------------------------------------------------------------------------- #


def _declared_methods(routes, is_api_route):
    """Return ``{path: frozenset(methods)}`` for one half of a route table.

    ``routes`` is an ``app.routes`` sequence.  ``is_api_route`` selects the
    application's own operations when true and the routes FastAPI added for its
    documentation when false.  ``APIRoute`` derives from
    ``starlette.routing.Route``, so an ``isinstance`` test against ``APIRoute``
    is what separates the two halves; a test against ``Route`` would match
    every entry.
    """
    return {
        route.path: frozenset(route.methods)
        for route in routes
        if isinstance(route, APIRoute) is is_api_route
    }


def _absolute_url(client, path):
    """Return ``path`` resolved against ``client``'s base URL.

    A ``location`` header carries an absolute URL, and the origin half of it is
    whatever base URL ``TestClient`` was constructed with.  ``httpx``
    normalises a base URL to end in ``/``, so the separator is stripped before
    joining.
    """
    return "{origin}{path}".format(
        origin=str(client.base_url).rstrip("/"), path=path
    )


@pytest.fixture
def route_modules(main_module):
    """Return the four modules ``app/main.py`` line 3 imports, keyed by name.

    ``app.api.routes.config`` and ``app.core.config`` share a trailing name
    component, so every module is bound to an alias and reached through the
    returned mapping; no bare name in this module is shadowed.

    ``main_module`` is requested because ``app/api/routes/tweets.py`` lines 6
    and 7 import ``TwitterService`` and ``LLMService``, which no production
    module defines.  The ``app_module`` fixture in ``backend/tests/conftest.py``
    installs the fail-closed shims that make those imports resolve and leaves
    the module cached, so the objects returned here are the ones ``app.main``
    included.
    """
    from app.api.routes import analytics as analytics_routes
    from app.api.routes import config as config_routes
    from app.api.routes import tweets as tweets_routes
    from app.api.routes import users as users_routes

    return {
        "tweets": tweets_routes,
        "users": users_routes,
        "analytics": analytics_routes,
        "config": config_routes,
    }


# --------------------------------------------------------------------------- #
# The 404 census.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("method", "path"), ABSENT_OPERATIONS)
def test_absent_route_returns_404(client, method, path):
    """``method path`` answers ``404``: no router declares it.

    Seven of the nine cases are operations ``backend/tests/test_api.py``
    asserted a success status for.  ``GET /health`` is the route
    ``docker-compose.yml`` and ``cd.yml`` probe, and ``POST /token`` is the
    endpoint ``OAuth2PasswordBearer(tokenUrl="token")`` names.  None of the nine
    is implemented, and none is created to satisfy this suite.
    """
    response = client.request(method, path)

    assert response.status_code == NOT_FOUND_STATUS


def test_absent_route_404_is_the_router_default(client):
    """An unrouted request carries starlette's own ``404`` body.

    ``app/api/routes/tweets.py`` line 20 raises
    ``HTTPException(404, "Tweet not found")``, so ``404`` alone is consistent
    with a matched route rejecting a request.  ``{"detail": "Not Found"}`` is
    the body only the router produces, and it is what makes the census an
    assertion about absence.
    """
    response = client.get(UNROUTED_SAMPLE_PATH)

    assert response.status_code == NOT_FOUND_STATUS
    assert response.json() == ROUTER_NOT_FOUND_BODY


# --------------------------------------------------------------------------- #
# The two legacy paths the router does not answer with 404.
# --------------------------------------------------------------------------- #


def test_implemented_path_rejects_unsupported_method(client):
    """``DELETE /tweets/1`` answers ``405``, not ``404``.

    The path matches ``/tweets/{tweet_id}``, whose only declared method is
    ``GET``, so the router reports the method as not allowed and advertises the
    one it accepts.  ``backend/tests/test_api.py``'s ``test_delete_tweet``
    asserted ``204`` here; no ``DELETE`` route exists on any path.
    """
    response = client.request("DELETE", TWEET_DETAIL_REQUEST_PATH)

    assert response.status_code == METHOD_NOT_ALLOWED_STATUS
    assert response.status_code != NOT_FOUND_STATUS
    assert response.headers["allow"] == EXPECTED_ALLOW_HEADER
    assert response.json() == ROUTER_METHOD_NOT_ALLOWED_BODY


def test_trailing_slash_on_tweets_collection_redirects(client):
    """``POST /tweets/`` answers ``307`` to ``/tweets``, then ``405``.

    ``/tweets/`` matches no route, and ``app.router.redirect_slashes`` is at its
    default, so the router redirects to the slash-free form rather than
    reporting ``404``.  Following the redirect reaches ``/tweets``, which
    declares ``GET`` only, so the status a client observes by default is ``405``.
    ``backend/tests/test_api.py``'s ``test_create_tweet`` asserted ``201`` here
    and its ``test_unauthorized_access`` asserted ``401``; no route accepts a
    ``POST`` to the collection.
    """
    unfollowed = client.request(
        "POST", TWEETS_COLLECTION_TRAILING_SLASH_PATH, follow_redirects=False
    )

    assert unfollowed.status_code == TEMPORARY_REDIRECT_STATUS
    assert unfollowed.headers["location"] == _absolute_url(
        client, TWEETS_COLLECTION_PATH
    )

    followed = client.request("POST", TWEETS_COLLECTION_TRAILING_SLASH_PATH)

    assert followed.status_code == METHOD_NOT_ALLOWED_STATUS


# --------------------------------------------------------------------------- #
# Declared method sets, and the HEAD behaviour that follows from them.
# --------------------------------------------------------------------------- #


def test_tweets_routes_declare_expected_methods(integration_app):
    """The three application operations declare GET, GET and POST.

    Asserted as a whole mapping, so a method added to a route, or a route added
    to the application, fails here.  ``HEAD`` is absent from both ``GET``
    entries: ``fastapi.routing.APIRoute`` does not synthesise it.
    """
    declared = _declared_methods(integration_app.routes, is_api_route=True)

    assert declared == EXPECTED_METHODS_BY_PATH


def test_builtin_routes_declare_get_and_head(integration_app):
    """Each of FastAPI's four documentation routes declares GET and HEAD.

    These are plain ``starlette.routing.Route`` objects, and starlette does
    synthesise ``HEAD`` from ``GET``.  Asserted as a whole mapping, so it also
    fixes the count of non-``APIRoute`` entries at four and is the contrast that
    locates the missing ``HEAD`` of
    :func:`test_tweets_routes_declare_expected_methods` in ``APIRoute`` rather
    than in the test.
    """
    declared = _declared_methods(integration_app.routes, is_api_route=False)

    assert declared == {path: BUILTIN_METHODS for path in FASTAPI_BUILTIN_PATHS}


def test_implemented_get_path_rejects_head(client):
    """``HEAD /tweets`` answers ``405``, advertising ``GET``.

    The request-level consequence of ``APIRoute`` declaring ``{"GET"}``: a
    ``HEAD`` of an implemented ``GET`` route is refused as a method the path
    does not allow.  A ``HEAD`` response carries no body, so only the status and
    the ``allow`` header are observable.
    """
    response = client.request("HEAD", TWEETS_COLLECTION_PATH)

    assert response.status_code == METHOD_NOT_ALLOWED_STATUS
    assert response.headers["allow"] == EXPECTED_ALLOW_HEADER


def test_builtin_documentation_route_serves_head(client):
    """``HEAD /docs`` answers ``200``.

    The same request shape that ``/tweets`` refuses, against a route starlette
    built, succeeds -- so the refusal above is a property of ``APIRoute`` and not
    of the transport or the client.
    """
    response = client.request("HEAD", SWAGGER_UI_PATH)

    assert response.status_code == OK_STATUS


# --------------------------------------------------------------------------- #
# No API_V1_STR prefixing.
# --------------------------------------------------------------------------- #


def test_api_v1_str_is_declared():
    """``settings.API_V1_STR`` is ``"/api/v1"``.

    The oracle the two tests below rest on: the constant exists, so their
    finding is that nothing uses it rather than that there is nothing to use.
    Both read the field itself, so this is the only place the literal appears.
    """
    assert config_module.settings.API_V1_STR == API_V1_STR_DECLARED


def test_no_route_carries_the_api_v1_prefix(integration_app):
    """No route path starts with ``settings.API_V1_STR``.

    Covers the documentation routes as well as the application's own, since
    neither ``include_routers`` nor ``FastAPI()`` passes a prefix anywhere.
    """
    prefix = config_module.settings.API_V1_STR

    prefixed = sorted(
        route.path
        for route in integration_app.routes
        if route.path.startswith(prefix)
    )

    assert prefixed == []


def test_api_v1_prefixed_path_returns_404(client):
    """A request under ``settings.API_V1_STR`` answers ``404``.

    The request-level form of the same fact: the prefix joined to the collection
    path is not a route, so the router refuses it outright.
    """
    prefixed_path = config_module.settings.API_V1_STR + TWEETS_COLLECTION_PATH

    response = client.get(prefixed_path)

    assert response.status_code == NOT_FOUND_STATUS


# --------------------------------------------------------------------------- #
# The exact route table.
# --------------------------------------------------------------------------- #


def test_route_table_contains_only_tweets_paths_and_fastapi_builtins(
    integration_app,
):
    """``app.routes`` holds exactly seven paths.

    Asserted by set equality: nothing beyond the three ``/tweets`` paths and
    FastAPI's four documentation paths is registered, so a path added anywhere
    fails here.
    """
    paths = {route.path for route in integration_app.routes}

    assert paths == EXPECTED_ROUTE_PATHS


def test_only_three_operations_are_implemented(integration_app):
    """The application declares three operations of its own.

    ``APIRoute`` entries are the ones the four included routers contributed;
    the documentation routes are plain ``Route`` objects and are excluded.
    Three, against the ten operations ``backend/tests/test_api.py`` asserted.
    """
    operations = [
        route for route in integration_app.routes if isinstance(route, APIRoute)
    ]

    assert len(operations) == IMPLEMENTED_OPERATION_COUNT


def test_openapi_schema_documents_only_the_three_tweets_operations(
    integration_app,
):
    """``app.openapi()["paths"]`` names the three ``/tweets`` operations.

    The published contract, which is what an external consumer reads, asserted
    separately from the route table: ``get`` on the collection, ``get`` on the
    detail path and ``post`` on the responses path, and nothing else.  The four
    documentation routes carry ``include_in_schema`` false and so are absent
    here although they are present in the route table.
    """
    documented = {
        path: frozenset(operations)
        for path, operations in integration_app.openapi()["paths"].items()
    }

    assert documented == EXPECTED_OPENAPI_OPERATIONS


@pytest.mark.parametrize("module_name", BARE_ROUTER_MODULE_NAMES)
def test_empty_routers_contribute_no_routes(route_modules, module_name):
    """``app/api/routes/<module_name>.py`` registers no route on its router.

    The module-level counterpart of the census: ``users``, ``analytics`` and
    ``config`` each exist only so ``app/main.py`` line 3 can import the name it
    imports, and each declares a bare ``APIRouter()``.  Asserted against the
    empty list, so a route added to any of the three fails here as well as at
    the request level.
    """
    router = route_modules[module_name].router

    assert router.routes == []


def test_tweets_router_contributes_three_routes(route_modules):
    """``app/api/routes/tweets.py`` registers three routes on its router.

    The other half of the structural claim: every operation the application
    serves comes from this one module.
    """
    router = route_modules["tweets"].router

    assert len(router.routes) == TWEETS_ROUTER_ROUTE_COUNT
    assert sorted(route.path for route in router.routes) == sorted(
        IMPLEMENTED_PATHS
    )

import pytest
from fastapi.routing import APIRoute
import app.core.config as config_module
pytestmark = pytest.mark.integration


NOT_FOUND_STATUS = 404
METHOD_NOT_ALLOWED_STATUS = 405
TEMPORARY_REDIRECT_STATUS = 307
OK_STATUS = 200
ROUTER_NOT_FOUND_BODY = {"detail": "Not Found"}
ROUTER_METHOD_NOT_ALLOWED_BODY = {"detail": "Method Not Allowed"}
API_V1_STR_DECLARED = "/api/v1"


TWEETS_COLLECTION_PATH = "/tweets"
TWEET_DETAIL_PATH = "/tweets/{tweet_id}"
TWEET_RESPONSES_PATH = "/tweets/{tweet_id}/responses"
IMPLEMENTED_PATHS = (
    TWEETS_COLLECTION_PATH,
    TWEET_DETAIL_PATH,
    TWEET_RESPONSES_PATH,
)
FASTAPI_BUILTIN_PATHS = (
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
)
EXPECTED_ROUTE_PATHS = frozenset(IMPLEMENTED_PATHS + FASTAPI_BUILTIN_PATHS)
IMPLEMENTED_OPERATION_COUNT = 3
EXPECTED_METHODS_BY_PATH = {
    TWEETS_COLLECTION_PATH: frozenset({"GET"}),
    TWEET_DETAIL_PATH: frozenset({"GET"}),
    TWEET_RESPONSES_PATH: frozenset({"POST"}),
}
BUILTIN_METHODS = frozenset({"GET", "HEAD"})
EXPECTED_OPENAPI_OPERATIONS = {
    TWEETS_COLLECTION_PATH: frozenset({"get"}),
    TWEET_DETAIL_PATH: frozenset({"get"}),
    TWEET_RESPONSES_PATH: frozenset({"post"}),
}
EXPECTED_ALLOW_HEADER = "GET"


TWEET_DETAIL_REQUEST_PATH = "/tweets/1"
TWEETS_COLLECTION_TRAILING_SLASH_PATH = "/tweets/"
UNROUTED_SAMPLE_PATH = "/users/1"
SWAGGER_UI_PATH = "/docs"
BARE_ROUTER_MODULE_NAMES = ("users", "analytics", "config")
TWEETS_ROUTER_ROUTE_COUNT = 3
JSON_CONTENT_TYPE = "application/json"

# The path prefix `frontend/src/services/api.ts` produces while
# `REACT_APP_API_BASE_URL` is unset: it interpolates the variable with no
# fallback, so the base URL is the literal string `undefined`.
UNSET_BASE_PREFIX = "/undefined"
UNSET_BASE_TWEETS_COLLECTION_PATH = UNSET_BASE_PREFIX + TWEETS_COLLECTION_PATH
CLIENT_UNSET_BASE_OPERATIONS = (
    pytest.param("GET", UNSET_BASE_TWEETS_COLLECTION_PATH, id="get-unset-base-tweets"),
    pytest.param(
        "GET", UNSET_BASE_PREFIX + TWEET_DETAIL_REQUEST_PATH, id="get-unset-base-tweet-detail"
    ),
    pytest.param(
        "POST",
        UNSET_BASE_PREFIX + TWEET_DETAIL_REQUEST_PATH + "/responses",
        id="post-unset-base-tweet-responses",
    ),
    pytest.param(
        "POST", UNSET_BASE_PREFIX + "/generate-response", id="post-unset-base-generate-response"
    ),
)
CLIENT_UNSET_BASE_QUERY_STRINGS = (
    pytest.param("", id="no-query"),
    pytest.param("?page=2&limit=10", id="fetchTweets-well-formed"),
    pytest.param("?page=5&limit=undefined", id="getLatestTweets-uncoercible-limit"),
    pytest.param("?page=undefined&limit=undefined", id="dashboard-both-uncoercible"),
)


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


BAD_REQUEST_STATUS = 400

EXPECTED_MIDDLEWARE_CLASS_NAMES = frozenset({"CORSMiddleware"})

HOST_VALIDATING_MIDDLEWARE_CLASS_NAME = "TrustedHostMiddleware"

HOSTILE_HOST = "attacker.example"

HOSTILE_HOST_LOCATION = "http://attacker.example/tweets"

HOSTILE_HOST_REDIRECTS = (
    pytest.param(HOSTILE_HOST, HOSTILE_HOST_LOCATION, id="plain-attacker-host"),
    pytest.param(
        "attacker.example:8443",
        "http://attacker.example:8443/tweets",
        id="attacker-host-with-port",
    ),
    pytest.param(
        "user@attacker.example",
        "http://user@attacker.example/tweets",
        id="attacker-host-with-userinfo",
    ),
    pytest.param(
        "attacker.example/evil",
        "http://attacker.example/evil/tweets",
        id="attacker-host-with-path-segment",
    ),
    pytest.param(
        "https://attacker.example",
        "http://https://attacker.example/tweets",
        id="attacker-host-with-scheme",
    ),
    pytest.param("", "http:///tweets", id="empty-host"),
    pytest.param(
        "attacker example",
        "http://attacker%20example/tweets",
        id="host-containing-a-space",
    ),
    pytest.param(
        "[::1]:8000", "http://[::1]:8000/tweets", id="bracketed-ipv6-host"
    ),
    pytest.param(
        "attacker.example,good.example",
        "http://attacker.example,good.example/tweets",
        id="comma-joined-host-pair",
    ),
)

HOST_HEADER = "host"

HOSTILE_HOST_UNREFUSED_STATUS = TEMPORARY_REDIRECT_STATUS


def _declared_methods(routes, is_api_route):
    """Split APIRoute application routes from Starlette documentation routes
    before collecting method sets.
    """
    return {
        route.path: frozenset(route.methods)
        for route in routes
        if isinstance(route, APIRoute) is is_api_route
    }


def _absolute_url(client, path):
    return "{origin}{path}".format(
        origin=str(client.base_url).rstrip("/"), path=path
    )


@pytest.fixture
def route_modules(main_module):
    """Import route modules only after main_module installs the missing-symbol
    shims they require.
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


@pytest.mark.parametrize(("method", "path"), ABSENT_OPERATIONS)
def test_absent_route_returns_404(client, method, path):
    response = client.request(method, path)

    assert response.status_code == NOT_FOUND_STATUS


def test_absent_route_404_is_the_router_default(client):
    response = client.get(UNROUTED_SAMPLE_PATH)

    assert response.status_code == NOT_FOUND_STATUS
    assert response.json() == ROUTER_NOT_FOUND_BODY


def test_implemented_path_rejects_unsupported_method(client):
    response = client.request("DELETE", TWEET_DETAIL_REQUEST_PATH)

    assert response.status_code == METHOD_NOT_ALLOWED_STATUS
    assert response.status_code != NOT_FOUND_STATUS
    assert response.headers["allow"] == EXPECTED_ALLOW_HEADER
    assert response.json() == ROUTER_METHOD_NOT_ALLOWED_BODY


def test_trailing_slash_on_tweets_collection_redirects(client):
    unfollowed = client.request(
        "POST", TWEETS_COLLECTION_TRAILING_SLASH_PATH, follow_redirects=False
    )

    assert unfollowed.status_code == TEMPORARY_REDIRECT_STATUS
    assert unfollowed.headers["location"] == _absolute_url(
        client, TWEETS_COLLECTION_PATH
    )

    followed = client.request("POST", TWEETS_COLLECTION_TRAILING_SLASH_PATH)

    assert followed.status_code == METHOD_NOT_ALLOWED_STATUS


def test_tweets_routes_declare_expected_methods(integration_app):
    declared = _declared_methods(integration_app.routes, is_api_route=True)

    assert declared == EXPECTED_METHODS_BY_PATH


def test_builtin_routes_declare_get_and_head(integration_app):
    declared = _declared_methods(integration_app.routes, is_api_route=False)

    assert declared == {path: BUILTIN_METHODS for path in FASTAPI_BUILTIN_PATHS}


def test_implemented_get_path_rejects_head(client):
    response = client.request("HEAD", TWEETS_COLLECTION_PATH)

    assert response.status_code == METHOD_NOT_ALLOWED_STATUS
    assert response.headers["allow"] == EXPECTED_ALLOW_HEADER


def test_builtin_documentation_route_serves_head(client):
    response = client.request("HEAD", SWAGGER_UI_PATH)

    assert response.status_code == OK_STATUS


def test_api_v1_str_is_declared():
    assert config_module.settings.API_V1_STR == API_V1_STR_DECLARED


def test_no_route_carries_the_api_v1_prefix(integration_app):
    prefix = config_module.settings.API_V1_STR

    prefixed = sorted(
        route.path
        for route in integration_app.routes
        if route.path.startswith(prefix)
    )

    assert prefixed == []


def test_api_v1_prefixed_path_returns_404(client):
    prefixed_path = config_module.settings.API_V1_STR + TWEETS_COLLECTION_PATH

    response = client.get(prefixed_path)

    assert response.status_code == NOT_FOUND_STATUS


@pytest.mark.parametrize(("method", "path"), CLIENT_UNSET_BASE_OPERATIONS)
def test_client_unset_base_path_returns_404(client, method, path):
    """Every path the frontend emits today is unrouted, and answers ``404``.

    ``frontend/src/services/api.ts`` line 5 reads ``REACT_APP_API_BASE_URL``
    with no fallback, so with the variable unset every URL it builds begins with
    the literal four-character string ``undefined`` -- ``undefined/tweets``,
    which a browser resolves to the path ``/undefined/tweets``.  No router
    declares anything under that segment, so starlette's router refuses the
    request and the whole client surface reaches nothing.

    The body is asserted as well as the status, because the two ``404``\\ s on
    this surface are not the same fact: this one is the router refusing a path,
    while the ``HTTPException(404, "Tweet not found")`` written into
    ``app/api/routes/tweets.py`` is a handler branch that is unreachable (see
    ``test_http_tweets.py``).  Only the router's own
    ``{"detail":"Not Found"}`` appears here.

    This is the server-side oracle for the frontend msw layer:
    ``frontend/src/test-utils/handlers.ts`` ``unsetBaseBackendHandlers()``
    answers exactly this status, body and content type, and
    ``frontend/src/test-utils/handlers.test.ts`` asserts it does.
    """
    response = client.request(method, path)

    assert response.status_code == NOT_FOUND_STATUS
    assert response.json() == ROUTER_NOT_FOUND_BODY
    assert response.headers["content-type"] == JSON_CONTENT_TYPE


@pytest.mark.parametrize("query", CLIENT_UNSET_BASE_QUERY_STRINGS)
def test_client_unset_base_path_returns_404_whatever_the_query(client, query):
    """Routing decides the outcome before any query value is coerced.

    The collection request the frontend emits carries ``page``, which the route
    does not declare, and -- from ``twitterService.getLatestTweets`` and from
    ``components/Dashboard`` -- a ``limit`` of the literal string ``undefined``,
    which could not be coerced to ``int``.  Neither matters at this path: the
    ``404`` is identical for a well-formed query and a malformed one, which is
    what makes the routing failure, not the validation failure, the current
    behaviour of the assembled application.

    The ``422`` those same query values do produce is reachable only once the
    path is one the router declares; ``test_http_tweets.py`` asserts it there.
    """
    response = client.get(UNSET_BASE_TWEETS_COLLECTION_PATH + query)

    assert response.status_code == NOT_FOUND_STATUS
    assert response.json() == ROUTER_NOT_FOUND_BODY


def test_no_route_carries_the_unset_base_prefix(integration_app):
    """No declared route lives under the prefix the client's unset base URL produces."""
    prefixed = sorted(
        route.path
        for route in integration_app.routes
        if route.path.startswith(UNSET_BASE_PREFIX)
    )

    assert prefixed == []


def test_route_table_contains_only_tweets_paths_and_fastapi_builtins(
    integration_app,
):
    paths = {route.path for route in integration_app.routes}

    assert paths == EXPECTED_ROUTE_PATHS


def test_only_three_operations_are_implemented(integration_app):
    operations = [
        route for route in integration_app.routes if isinstance(route, APIRoute)
    ]

    assert len(operations) == IMPLEMENTED_OPERATION_COUNT


def test_openapi_schema_documents_only_the_three_tweets_operations(
    integration_app,
):
    documented = {
        path: frozenset(operations)
        for path, operations in integration_app.openapi()["paths"].items()
    }

    assert documented == EXPECTED_OPENAPI_OPERATIONS


@pytest.mark.parametrize("module_name", BARE_ROUTER_MODULE_NAMES)
def test_empty_routers_contribute_no_routes(route_modules, module_name):
    router = route_modules[module_name].router

    assert router.routes == []


def test_tweets_router_contributes_three_routes(route_modules):
    router = route_modules["tweets"].router

    assert len(router.routes) == TWEETS_ROUTER_ROUTE_COUNT
    assert sorted(route.path for route in router.routes) == sorted(
        IMPLEMENTED_PATHS
    )


@pytest.mark.parametrize(
    ("host_header", "expected_location"), HOSTILE_HOST_REDIRECTS
)
def test_slash_redirect_reflects_request_host(
    client, host_header, expected_location
):
    """The ``location`` of the slash redirect is built from ``Host``, verbatim.

    ``POST /tweets/`` matches no route, so starlette redirects to the slash-free
    form and, because a ``location`` carries an absolute URL, has to choose an
    origin for it.  It takes the request's own ``Host``, unvalidated: every value
    in :data:`HOSTILE_HOST_REDIRECTS` -- including one carrying a port, one
    carrying userinfo, one carrying an extra path segment, one carrying a scheme,
    the empty value, one containing a space, a bracketed IPv6 literal and a
    comma-joined pair -- appears in the target the client is told to follow.

    The consequence is an open-redirect primitive on a public, unauthenticated
    path: a victim who follows the redirect leaves for the attacker's host.  This
    is the request-level face of GHSA-86qp-5c8j-p5mr / CVE-2026-48710.
    """
    response = client.request(
        "POST",
        TWEETS_COLLECTION_TRAILING_SLASH_PATH,
        follow_redirects=False,
        headers={HOST_HEADER: host_header},
    )

    assert response.status_code == TEMPORARY_REDIRECT_STATUS
    assert response.headers["location"] == expected_location


@pytest.mark.parametrize(
    ("host_header", "expected_location"), HOSTILE_HOST_REDIRECTS
)
def test_no_host_value_is_refused(client, host_header, expected_location):
    """No ``Host`` value is rejected: each is answered ``307``, never ``400``.

    The complement of the assertion above, and the half that names the absence
    rather than the reflection.  A stack that validated the header would answer a
    host outside its allow-list with ``400`` and never emit a ``location`` at all;
    this one emits one for every spelling probed, malformed values included.

    ``expected_location`` is unused deliberately: the parametrisation is shared
    with :func:`test_slash_redirect_reflects_request_host` so the two cannot drift
    onto different host sets, and this case asserts only the disposition.
    """
    response = client.request(
        "POST",
        TWEETS_COLLECTION_TRAILING_SLASH_PATH,
        follow_redirects=False,
        headers={HOST_HEADER: host_header},
    )

    assert response.status_code == HOSTILE_HOST_UNREFUSED_STATUS
    assert response.status_code != BAD_REQUEST_STATUS
    assert "location" in response.headers


def test_slash_redirect_location_tracks_host_not_client_base_url(client):
    """The reflected origin is the request's ``Host``, not the client's base URL.

    ``TestClient`` is constructed with ``http://testserver``, which is what
    :func:`_absolute_url` reads and what
    :func:`test_trailing_slash_on_tweets_collection_redirects` therefore observes.
    Sending a ``Host`` replaces the origin in the ``location`` outright, so the
    trusted value in that test is a property of the client rather than of the
    application: two requests to one path, differing only in a header, are
    redirected to two different origins.
    """
    trusted = client.request(
        "POST", TWEETS_COLLECTION_TRAILING_SLASH_PATH, follow_redirects=False
    )
    hostile = client.request(
        "POST",
        TWEETS_COLLECTION_TRAILING_SLASH_PATH,
        follow_redirects=False,
        headers={HOST_HEADER: HOSTILE_HOST},
    )

    assert trusted.headers["location"] == _absolute_url(
        client, TWEETS_COLLECTION_PATH
    )
    assert hostile.headers["location"] == HOSTILE_HOST_LOCATION
    assert hostile.headers["location"] != trusted.headers["location"]


def test_application_installs_no_host_validating_middleware(integration_app):
    """``user_middleware`` holds ``CORSMiddleware`` and nothing else.

    The structural reason the reflection above is reachable.  ``app/main.py``
    line 41 runs ``configure_cors(app)`` and adds no other middleware, so no
    ``TrustedHostMiddleware`` -- the class starlette documents as the protection
    against ``Host``-header attacks -- stands between the request and the router.

    Asserted by set equality rather than by absence alone, so adding any
    middleware fails this test and forces the census above to be re-measured.
    Installing the validator is a production change outside the two authorized
    touches, so this asserts the gap; it does not close it.
    """
    installed = frozenset(
        entry.cls.__name__ for entry in integration_app.user_middleware
    )

    assert installed == EXPECTED_MIDDLEWARE_CLASS_NAMES
    assert HOST_VALIDATING_MIDDLEWARE_CLASS_NAME not in installed

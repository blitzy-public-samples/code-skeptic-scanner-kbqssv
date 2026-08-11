from unittest.mock import MagicMock, patch

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

pytestmark = pytest.mark.integration


EXPECTED_ALLOWED_ORIGINS = []

EXPECTED_ALLOW_METHODS = ["*"]

EXPECTED_ALLOW_HEADERS = ["*"]

EXPECTED_CORS_OPTION_NAMES = (
    "allow_credentials",
    "allow_headers",
    "allow_methods",
    "allow_origins",
)

EXPECTED_PROJECT_NAME = "Twitter Bot"

DEFAULT_FASTAPI_TITLE = "FastAPI"

TWEETS_ROUTER_ROUTE_COUNT = 3

EXPECTED_STARTUP_HANDLER_NAMES = ["startup_event"]
EXPECTED_SHUTDOWN_HANDLER_NAMES = ["shutdown_event"]

TWEETS_PATH = "/tweets"

OPENAPI_PATH = "/openapi.json"

ARBITRARY_ORIGIN = "http://arbitrary.example"

HTTP_OK = 200

DISALLOWED_PREFLIGHT_STATUS = 400
DISALLOWED_PREFLIGHT_BODY = "Disallowed CORS origin"

ACCESS_CONTROL_ALLOW_ORIGIN = "access-control-allow-origin"
ACCESS_CONTROL_ALLOW_CREDENTIALS = "access-control-allow-credentials"
ACCESS_CONTROL_ALLOW_METHODS = "access-control-allow-methods"
ACCESS_CONTROL_MAX_AGE = "access-control-max-age"

#: What the CORS middleware emits on a *refused* preflight, which is the whole
#: point of the pair below: the refusal still advertises the surface.
PREFLIGHT_ADVERTISED_METHODS = "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT"
PREFLIGHT_ADVERTISED_MAX_AGE = "600"

METHOD_NOT_ALLOWED_STATUS = 405
NOT_FOUND_STATUS = 404
UNPROCESSABLE_ENTITY_STATUS = 422

ROUTER_METHOD_NOT_ALLOWED_BODY = {"detail": "Method Not Allowed"}
TWEETS_ALLOW_HEADER = "GET"

UNROUTED_PATH = "/users/1"

#: Every header this application would have to emit for a browser to be given
#: any of the defence-in-depth controls a public HTTP surface is expected to
#: carry. `app/main.py` installs `CORSMiddleware` and nothing else, so none of
#: them is ever set -- on any status.
ABSENT_SECURITY_HEADERS = (
    "x-content-type-options",
    "x-frame-options",
    "content-security-policy",
    "strict-transport-security",
    "referrer-policy",
    "permissions-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
    "cache-control",
)

#: The headers the application itself sets, by status. `date`, `server` and the
#: connection headers are the *server's* and are absent here by construction: the
#: in-process ASGI transport delivers exactly what the application emitted, which
#: is the boundary under test.
APPLICATION_HEADER_SETS = (
    pytest.param(OPENAPI_PATH, HTTP_OK, ("content-length", "content-type"), id="200-openapi"),
    pytest.param(
        UNROUTED_PATH, NOT_FOUND_STATUS, ("content-length", "content-type"), id="404-unrouted"
    ),
)

#: A token no verifier could accept, since `app/core/security.py` defines none.
BOGUS_BEARER_HEADER = {"Authorization": "Bearer totally-bogus"}


def _header_names(response):
    return tuple(sorted(name.lower() for name in response.headers))


def _cors_middleware_entries(application):
    return [
        entry
        for entry in application.user_middleware
        if entry.cls is CORSMiddleware
    ]


def _application_operations(application):
    """Split the application's own APIRoute entries from Starlette
    documentation routes.
    """
    return [
        route for route in application.routes if isinstance(route, APIRoute)
    ]


def test_configure_cors_uses_empty_allowed_origins(main_module):
    assert main_module.settings.ALLOWED_ORIGINS == EXPECTED_ALLOWED_ORIGINS


def test_cors_middleware_registered_with_expected_options(integration_app):
    cors_entries = _cors_middleware_entries(integration_app)
    assert len(cors_entries) == 1

    options = cors_entries[0].options
    assert options["allow_origins"] == EXPECTED_ALLOWED_ORIGINS
    assert options["allow_credentials"] is True
    assert options["allow_methods"] == EXPECTED_ALLOW_METHODS
    assert options["allow_headers"] == EXPECTED_ALLOW_HEADERS
    assert tuple(sorted(options)) == EXPECTED_CORS_OPTION_NAMES


def test_cors_middleware_registered_exactly_once(integration_app):
    assert len(_cors_middleware_entries(integration_app)) == 1


def test_cors_headers_absent_for_arbitrary_origin(client):
    response = client.get(OPENAPI_PATH, headers={"Origin": ARBITRARY_ORIGIN})

    assert response.status_code == HTTP_OK
    assert ACCESS_CONTROL_ALLOW_ORIGIN not in response.headers
    assert response.headers[ACCESS_CONTROL_ALLOW_CREDENTIALS] == "true"


def test_cors_preflight_rejects_arbitrary_origin(client):
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


def test_refused_preflight_still_advertises_the_whole_method_surface(client):
    """The 400 carries `allow-methods` and `max-age` anyway.

    `allow_methods=["*"]` is expanded by the middleware into all seven verbs, and
    it writes that list plus a ten-minute cache directive *before* deciding the
    origin is disallowed.  So the refusal is simultaneously a disclosure of the
    method surface and an instruction to cache the refusal.  Asserted because a
    reader who saw only the previous test would conclude a refused preflight
    reveals nothing.
    """
    response = client.options(
        TWEETS_PATH,
        headers={
            "Origin": ARBITRARY_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == DISALLOWED_PREFLIGHT_STATUS
    assert response.headers[ACCESS_CONTROL_ALLOW_METHODS] == PREFLIGHT_ADVERTISED_METHODS
    assert response.headers[ACCESS_CONTROL_MAX_AGE] == PREFLIGHT_ADVERTISED_MAX_AGE
    assert response.headers[ACCESS_CONTROL_ALLOW_CREDENTIALS] == "true"


def test_options_without_an_origin_is_not_a_preflight_at_all(client_no_raise):
    """Without an `Origin` the request falls through to the router and answers 405.

    The middleware treats a request as a preflight only when it carries both
    `Origin` and `Access-Control-Request-Method`; otherwise it passes it on, and
    the tweets router declares `GET` alone.  So the two ways of asking the same
    question fail differently -- **400** with an origin, **405** without one --
    and neither is a usable preflight.  Together with the test above, that is the
    whole finding: no cross-origin browser client can call this API, whatever
    origin it presents, until `ALLOWED_ORIGINS` is populated.
    """
    response = client_no_raise.options(TWEETS_PATH)

    assert response.status_code == METHOD_NOT_ALLOWED_STATUS
    assert response.json() == ROUTER_METHOD_NOT_ALLOWED_BODY
    assert response.headers["allow"] == TWEETS_ALLOW_HEADER
    assert ACCESS_CONTROL_ALLOW_METHODS not in response.headers


def test_a_data_bearing_route_answers_an_origin_with_credentials_but_no_origin(
    client, mock_db, override_get_db
):
    """The same half-granted header pair on the route that carries data.

    `test_cors_headers_absent_for_arbitrary_origin` establishes this on the
    built-in `/openapi.json`; asserted again on `/tweets` because that is the
    route a browser client actually calls, and because the trap only matters
    where a body is at stake: the middleware emits the credentials flag
    unconditionally and the origin header only for an allowed origin, so with
    `ALLOWED_ORIGINS = []` the server records a `200` with a complete body while
    the browser discards every byte of it.
    """
    override_get_db(mock_db)
    chain = mock_db.query.return_value.offset.return_value.limit.return_value
    chain.all.return_value = []

    response = client.get(TWEETS_PATH, headers={"Origin": ARBITRARY_ORIGIN})

    assert response.status_code == HTTP_OK
    assert response.json() == []
    assert response.headers[ACCESS_CONTROL_ALLOW_CREDENTIALS] == "true"
    assert ACCESS_CONTROL_ALLOW_ORIGIN not in response.headers


# --------------------------------------------------------------------------- #
# The application sets no security response header on any status               #
# --------------------------------------------------------------------------- #
# `app/main.py` installs exactly one middleware, `CORSMiddleware`, so nothing in
# the stack contributes a header beyond the ones the response itself needs.  The
# consequence is asserted per status rather than once, because a reader auditing
# a single successful response could not otherwise tell whether an error path
# hardens where the happy path does not.


@pytest.mark.parametrize("path, expected_status, expected_headers", APPLICATION_HEADER_SETS)
def test_application_emits_exactly_the_headers_the_response_needs(
    client, path, expected_status, expected_headers
):
    """The emitted header set is the payload's own, with nothing added."""
    response = client.get(path)

    assert response.status_code == expected_status
    assert _header_names(response) == expected_headers


@pytest.mark.parametrize("header_name", ABSENT_SECURITY_HEADERS)
def test_no_security_header_accompanies_a_successful_response(client, header_name):
    """None of the standard browser-facing controls is set on a `200`."""
    response = client.get(OPENAPI_PATH)

    assert response.status_code == HTTP_OK
    assert header_name not in response.headers


@pytest.mark.parametrize("header_name", ABSENT_SECURITY_HEADERS)
def test_no_security_header_accompanies_an_error_response(client_no_raise, header_name):
    """Nor on a `404`, a `405` or a `422` -- the error paths harden nothing either."""
    for response in (
        client_no_raise.get(UNROUTED_PATH),
        client_no_raise.request("HEAD", TWEETS_PATH),
        client_no_raise.get(TWEETS_PATH, params={"limit": "undefined"}),
    ):
        assert response.status_code in (
            NOT_FOUND_STATUS,
            METHOD_NOT_ALLOWED_STATUS,
            UNPROCESSABLE_ENTITY_STATUS,
        )
        assert header_name not in response.headers


def test_the_json_content_type_is_the_only_control_on_a_payload_bearing_response(client):
    """With no `nosniff`, the content type alone decides how a browser treats a body.

    A response whose body carries stored markup is inert when navigated to
    directly *because* it is declared `application/json`.  Nothing backs that
    declaration up: `x-content-type-options` is absent, so a client that sniffs
    is not prevented from doing so.  Asserted on `/openapi.json`, which is a
    `200` needing no injected data and whose body is attacker-influenced in the
    same sense -- it echoes every declared path.
    """
    response = client.get(OPENAPI_PATH)

    assert response.headers["content-type"] == "application/json"
    assert "x-content-type-options" not in response.headers


def test_the_schema_declares_no_security_scheme_and_no_route_requires_one(
    integration_app, client
):
    """Nothing on this surface authenticates, and the document says so.

    The generated OpenAPI has no `securitySchemes` and no operation-level
    `security`, and a token no verifier could accept is answered exactly as an
    anonymous request is.  This is the design gap recorded rather than closed:
    `app/api/dependencies.py` defines `get_current_user`, no route depends on it,
    and the `verify_token` it imports does not exist.
    """
    schema = integration_app.openapi()

    assert "securitySchemes" not in schema.get("components", {})
    assert "security" not in schema
    for operations in schema["paths"].values():
        for operation in operations.values():
            assert "security" not in operation

    anonymous = client.get(OPENAPI_PATH)
    with_bogus_token = client.get(OPENAPI_PATH, headers=BOGUS_BEARER_HEADER)

    assert with_bogus_token.status_code == anonymous.status_code == HTTP_OK
    assert with_bogus_token.content == anonymous.content


# Import route modules inside tests while the app_module shim fixture is
# active; module-scope import would fail collection.


def test_include_routers_is_called_for_four_routers_only_one_of_which_contributes_routes(
    integration_app, main_module
):
    from app.api.routes import analytics as analytics_routes
    from app.api.routes import config as config_routes
    from app.api.routes import tweets as tweets_routes
    from app.api.routes import users as users_routes

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
    from app.api.routes import tweets as tweets_routes

    operations = _application_operations(integration_app)
    declared_routes = tweets_routes.router.routes
    wired_endpoints = [route.endpoint for route in operations]
    declared_endpoints = [route.endpoint for route in declared_routes]

    assert wired_endpoints == declared_endpoints
    assert len(wired_endpoints) == TWEETS_ROUTER_ROUTE_COUNT


# Assert lifecycle handlers by registration and call counts only; entering
# TestClient lifespan would reach live startup boundaries.


def test_startup_and_shutdown_handlers_are_registered(integration_app):
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
    mock_get_db = MagicMock(name="mock_get_db")

    with patch.object(main_module, "get_db", mock_get_db):
        response = client.get(OPENAPI_PATH)
        client.close()

    assert response.status_code == HTTP_OK
    assert mock_get_db.call_count == 0


def test_app_is_constructed_without_project_name(integration_app, main_module):
    assert main_module.settings.PROJECT_NAME == EXPECTED_PROJECT_NAME
    assert integration_app.title == DEFAULT_FASTAPI_TITLE

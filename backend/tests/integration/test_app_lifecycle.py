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

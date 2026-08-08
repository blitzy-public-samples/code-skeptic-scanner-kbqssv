"""Integration suite for ``app/api/routes/tweets.py``, the HTTP surface.

The subject is the only production module in this repository that declares
endpoints.  It declares exactly three, and this suite exercises all three over
starlette's in-process ASGI transport:

===== =================================== =========================
Verb  Path                                Handler
===== =================================== =========================
GET   ``/tweets``                         ``get_tweets`` (line 12)
GET   ``/tweets/{tweet_id}``              ``get_tweet`` (line 17)
POST  ``/tweets/{tweet_id}/responses``    ``generate_response`` (line 24)
===== =================================== =========================

No route carries the ``API_V1_STR`` prefix, and the ``users``, ``analytics``
and ``config`` routers ``app/main.py`` also includes are bare.  The census of
paths that are *absent* belongs to
``backend/tests/integration/test_route_surface.py``.

What this suite asserts
-----------------------
``GET /tweets``

* A single row reaches the client as ``200`` and a one-element JSON list whose
  object carries all ten field names ``app/schema/tweet.py`` declares, each
  holding the value ``make_tweet`` supplied.
* An empty result set is ``200`` and ``[]``, not ``404`` and not an error.
* ``skip`` and ``limit`` are query parameters and reach ``.offset(...)`` and
  ``.limit(...)`` unchanged, in that order.
* Omitting both applies the declared defaults, ``0`` and ``100``.
* A row missing a required field fails response-model validation and surfaces
  as ``500``.
* A failure raised by ``db.query(...)`` or by the terminal ``.all()``
  propagates as the instance that was raised, and surfaces as ``500`` through a
  client that reports; nothing later in the chain, and no serialization, runs.

Every path that reaches ``query``

* The model handed to ``db.query(...)`` is ``app.schema.tweet.Tweet`` itself --
  the same object the subject imported -- on all three operations.

``GET /tweets/{tweet_id}`` and ``POST /tweets/{tweet_id}/responses``

* Both raise ``AttributeError`` naming the missing attribute ``id``.
* Both surface as ``500`` through a client that reports handler exceptions.
* The failure precedes ``.filter(...)`` itself, so neither ``.filter`` nor
  ``.first`` is ever called, and ``LLMService`` is never constructed.

Recorded gaps

* No implemented operation declares a ``requestBody``.
* ``dependency_overrides`` is empty when a test begins.

Current behaviour captured as divergence
----------------------------------------
``Tweet.id`` does not exist.  ``app/schema/tweet.py`` declares ten fields and
``id`` is not among them, and pydantic v1 moves declared fields off the class
namespace, so ``Tweet.id`` resolves to nothing at all.  Both handlers that
filter -- line 18 and line 27 -- evaluate ``Tweet.id == tweet_id`` to build the
argument they pass to ``.filter(...)``, so the ``AttributeError`` is raised
before ``.filter`` is entered.  Its message is
``"type object 'Tweet' has no attribute 'id'"``.

Two consequences follow, and both are asserted:

* ``GET /tweets/{tweet_id}`` answers **500**, where the handler was written to
  answer 404.  The legacy ``backend/tests/test_api.py::test_get_tweet``
  expected ``200``; neither status is reachable.
* The ``404`` guard on lines 19-20 and 28-29 is **unreachable**.  It is written
  for a falsy query result, but the exception is raised before any query result
  exists, so programming ``.first()`` to return ``None`` -- precisely the input
  the guard exists for -- still answers 500.

``POST /tweets/{tweet_id}/responses`` fails at line 27 and therefore never
reaches ``LLMService()`` at line 31, so no assertion here observes the LLM
boundary at all.  The subject also imports ``TwitterService`` at line 6 and
never references it, and line 34 defers persisting the generated response, so
nothing is written even on the path the handler cannot reach.

No implemented operation accepts a request body.  There is no ``Body(...)``,
no body model and no ``requestBody`` in the generated OpenAPI document, so an
expectation of ``422`` for a malformed body has no subject on this surface.

Scope
-----
Every test drives the application through a ``TestClient`` from this folder's
``conftest.py`` and injects its data with ``override_get_db``, so no request
reaches Firestore and none opens a socket.  Neither client is entered as a
context manager, so the ``startup`` handler -- which calls ``get_db()`` and
then ``await start_tweet_stream()`` -- never runs.

Covered elsewhere: the application object, its middleware and its lifecycle
handlers in ``backend/tests/integration/test_app_lifecycle.py``; the behaviour
of ``app/db/firestore.py`` in ``backend/tests/unit/test_db_firestore.py``.  The
injected stand-in here is a ``MagicMock``, and no test asserts anything about
the real module.

.. seealso::

   ``docs/testing/DECISION-LOG.md`` rows D53 (production defects are pinned, not
   repaired, which is what makes the 500 the oracle), D50-D51 (authorized touch
   #1, which this surface rests on), D28 and D107 (the ``TestClient`` lifecycle
   and the ``dependency_overrides`` contract).
   ``docs/testing/TRACEABILITY-MATRIX.md`` section G for the unreachable ``404``.
"""
import importlib
import pytest
from app.schema.tweet import Tweet
from tests.factories import make_tweet
pytestmark = pytest.mark.integration


TWEETS_PATH = "/tweets"
TWEET_ID = "1234567890"
TWEET_DETAIL_PATH = "/tweets/{0}".format(TWEET_ID)
TWEET_RESPONSES_PATH = "/tweets/{0}/responses".format(TWEET_ID)
OK_STATUS = 200
SERVER_ERROR_STATUS = 500
UNREACHABLE_NOT_FOUND_STATUS = 404
DEFAULT_SKIP = 0
DEFAULT_LIMIT = 100
EXPLICIT_SKIP = 5
EXPLICIT_LIMIT = 2
TWEET_FIELD_NAMES = (
    "tweet_id",
    "content",
    "user_id",
    "timestamp",
    "likes_count",
    "retweets_count",
    "doubt_rating",
    "ai_tools",
    "media_urls",
    "quoted_tweet_id",
)
SERIALIZED_TIMESTAMP = "2024-01-01T00:00:00"
OMITTED_REQUIRED_FIELD = "content"
MISSING_SCHEMA_ATTRIBUTE = "id"

#: Failure types injected into the collection endpoint's query chain.
#: ``Exception`` is included deliberately: it is the type a bare
#: ``except Exception`` would name, and the subject holds no ``try`` at all, so a
#: clause of that shape -- or a fallback returning an empty list -- would stop
#: these exceptions from arriving.  The other two are subclasses of it.
PROPAGATED_FAILURES = (
    pytest.param(Exception, id="exception"),
    pytest.param(RuntimeError, id="runtimeerror"),
    pytest.param(ConnectionError, id="connectionerror"),
)

#: Message of the failure injected into ``db.query(...)``.
QUERY_FAILURE_MESSAGE = "the query could not be issued"

#: Message of the failure injected into the terminal ``.all()``.
RESULT_READ_FAILURE_MESSAGE = "the result set could not be read"

#: Body starlette's ``ServerErrorMiddleware`` writes for an unhandled handler
#: exception, and the content type it writes it under.  A response carrying
#: these is a response the ``List[Tweet]`` response model never produced, which
#: is what makes them the oracle for "serialization did not run".
SERVER_ERROR_BODY = "Internal Server Error"
SERVER_ERROR_CONTENT_TYPE = "text/plain"

#: Import path of the subject.  Resolved through a fixture rather than at module
#: scope: line 6 does ``from app.services.twitter_service import
#: TwitterService``, a name that module does not define, so the subject imports
#: only under the shim ``backend/tests/conftest.py`` installs.
ROUTER_MODULE = "app.api.routes.tweets"

#: Every path template the subject registers, as it appears in the OpenAPI
#: document.  The ``requestBody`` assertion covers all three.
IMPLEMENTED_OPERATIONS = (
    pytest.param("get", "/tweets", id="get-tweets"),
    pytest.param("get", "/tweets/{tweet_id}", id="get-tweet-by-id"),
    pytest.param(
        "post", "/tweets/{tweet_id}/responses", id="post-tweet-responses"
    ),
)


QUERY_MODEL = Tweet

UNPROCESSABLE_ENTITY_STATUS = 422

MALFORMED_QUERY_VALUES = (
    pytest.param("skip", "abc", id="skip-non-numeric"),
    pytest.param("skip", "1.5", id="skip-fractional"),
    pytest.param("skip", "", id="skip-empty"),
    pytest.param("limit", "abc", id="limit-non-numeric"),
    pytest.param("limit", "1.5", id="limit-fractional"),
    pytest.param("limit", "", id="limit-empty"),
)

INTEGER_VALIDATION_MESSAGE = "value is not a valid integer"

INTEGER_VALIDATION_TYPE = "type_error.integer"

UNCONSTRAINED_QUERY_VALUES = (
    pytest.param({"skip": -1}, -1, DEFAULT_LIMIT, id="skip-negative"),
    pytest.param({"limit": 0}, DEFAULT_SKIP, 0, id="limit-zero"),
)


def _program_collection_rows(mock_db, rows):
    chain = mock_db.query.return_value.offset.return_value.limit.return_value
    chain.all.return_value = rows
    return mock_db


def _program_single_row(mock_db, row):
    mock_db.query.return_value.filter.return_value.first.return_value = row
    return mock_db


# The model every reaching path queries with.  The injected database is a
# ``MagicMock``, which answers ``query(anything)`` with the same child object, so
# the model each handler passes is only observable from the call record and is
# asserted explicitly wherever ``query`` is reached.


@pytest.fixture
def tweets_router_module(main_module):
    """Return the imported subject, ``app/api/routes/tweets.py``.

    Requesting :func:`main_module` is what makes the import possible: it applies
    the parent conftest's ``app_module`` fixture, which installs the stand-ins
    for the names the subject's import graph needs and imports ``app.main``,
    and ``app.main`` imports this router.  The module is therefore already
    resolved by the time this fixture reads it out of the cache.
    """
    return importlib.import_module(ROUTER_MODULE)


def test_router_binds_the_authoritative_tweet_model(tweets_router_module):
    """The model this suite asserts on is the object the subject queries with.

    ``app/api/routes/tweets.py`` line 5 does ``from app.schema.tweet import
    Tweet``, and this module imports the same name from the same place.  The
    identity check is what stops the assertions below from passing against a
    second, unrelated class that merely shares a name.
    """
    assert tweets_router_module.Tweet is Tweet


# GET /tweets -- the collection endpoint, the one operation that succeeds.


def test_get_tweets_returns_serialized_tweet(client, mock_db, override_get_db):
    override_get_db(mock_db)
    expected = make_tweet()
    _program_collection_rows(mock_db, [expected])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    _assert_queried_the_tweet_model(mock_db)
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    serialized = body[0]
    assert tuple(sorted(serialized)) == tuple(sorted(TWEET_FIELD_NAMES))
    assert serialized["tweet_id"] == expected["tweet_id"]
    assert serialized["content"] == expected["content"]
    assert serialized["user_id"] == expected["user_id"]
    assert serialized["timestamp"] == SERIALIZED_TIMESTAMP
    assert serialized["likes_count"] == expected["likes_count"]
    assert serialized["retweets_count"] == expected["retweets_count"]
    assert serialized["doubt_rating"] == expected["doubt_rating"]
    assert serialized["ai_tools"] == expected["ai_tools"]
    assert serialized["media_urls"] == expected["media_urls"]
    assert serialized["quoted_tweet_id"] is None


def test_get_tweets_returns_empty_list_when_no_rows(
    client, mock_db, override_get_db
):
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    assert response.json() == []
    _assert_queried_the_tweet_model(mock_db)


def test_get_tweets_passes_pagination_to_query(
    client, mock_db, override_get_db
):
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(
        TWEETS_PATH, params={"skip": EXPLICIT_SKIP, "limit": EXPLICIT_LIMIT}
    )

    assert response.status_code == OK_STATUS
    _assert_queried_the_tweet_model(mock_db)
    offset = mock_db.query.return_value.offset
    offset.assert_called_once_with(EXPLICIT_SKIP)
    offset.return_value.limit.assert_called_once_with(EXPLICIT_LIMIT)


def test_get_tweets_uses_default_pagination(client, mock_db, override_get_db):
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    _assert_queried_the_tweet_model(mock_db)
    offset = mock_db.query.return_value.offset
    offset.assert_called_once_with(DEFAULT_SKIP)
    offset.return_value.limit.assert_called_once_with(DEFAULT_LIMIT)


def test_get_tweets_response_validation_rejects_incomplete_row(
    client_no_raise, mock_db, override_get_db
):
    override_get_db(mock_db)
    incomplete = make_tweet()
    del incomplete[OMITTED_REQUIRED_FIELD]
    _program_collection_rows(mock_db, [incomplete])

    response = client_no_raise.get(TWEETS_PATH)

    assert response.status_code == SERVER_ERROR_STATUS


def test_get_tweets_queries_the_tweet_model(client, mock_db, override_get_db):
    """The collection handler passes ``Tweet`` to ``db.query``, once.

    Line 13 builds its whole chain off ``db.query(Tweet)``.  Any other argument
    -- ``User``, the module, a string -- traverses the same permissive
    ``MagicMock`` chain and answers ``200`` with the same body, so the argument
    is asserted rather than inferred from the response.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    mock_db.query.assert_called_once_with(Tweet)


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_get_tweets_propagates_a_query_failure(
    client, mock_db, override_get_db, failure_type
):
    """A failing ``db.query`` reaches the caller as the instance raised.

    The handler holds no ``try``, so nothing converts the failure into an empty
    list or a 4xx.  It is raised while the chain's first link is being built, so
    ``.offset`` -- and everything after it -- is never reached.
    """
    override_get_db(mock_db)
    failure = failure_type(QUERY_FAILURE_MESSAGE)
    mock_db.query.side_effect = failure

    with pytest.raises(failure_type) as excinfo:
        client.get(TWEETS_PATH)

    assert excinfo.value is failure
    assert str(excinfo.value) == QUERY_FAILURE_MESSAGE
    mock_db.query.assert_called_once_with(Tweet)
    mock_db.query.return_value.offset.assert_not_called()


def test_get_tweets_query_failure_returns_500(
    client_no_raise, mock_db, override_get_db
):
    """The same failure answers ``500`` through a client that reports.

    This is the status a caller observes.  The body is starlette's own
    server-error text under ``text/plain``, not a JSON list, which is what
    establishes that the ``List[Tweet]`` response model never ran.
    """
    override_get_db(mock_db)
    mock_db.query.side_effect = RuntimeError(QUERY_FAILURE_MESSAGE)

    response = client_no_raise.get(TWEETS_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.text == SERVER_ERROR_BODY
    assert response.headers["content-type"].startswith(
        SERVER_ERROR_CONTENT_TYPE
    )


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_get_tweets_propagates_a_result_read_failure(
    client, mock_db, override_get_db, failure_type
):
    """A failing terminal ``.all()`` reaches the caller as the instance raised.

    This is the last link of line 13's chain, so the failure arrives after
    ``query``, ``offset`` and ``limit`` have all succeeded: the handler got as
    far as reading the result set and still returns nothing.
    """
    override_get_db(mock_db)
    failure = failure_type(RESULT_READ_FAILURE_MESSAGE)
    chain = mock_db.query.return_value.offset.return_value.limit.return_value
    chain.all.side_effect = failure

    with pytest.raises(failure_type) as excinfo:
        client.get(TWEETS_PATH)

    assert excinfo.value is failure
    assert str(excinfo.value) == RESULT_READ_FAILURE_MESSAGE
    mock_db.query.assert_called_once_with(Tweet)
    chain.all.assert_called_once_with()


def test_get_tweets_result_read_failure_returns_500_without_serializing(
    client_no_raise, mock_db, override_get_db
):
    """A failing ``.all()`` answers ``500`` and serializes nothing.

    The response model is reached only with the value ``.all()`` returns, and it
    returned nothing, so the body is starlette's server-error text rather than
    the JSON array a successful request produces.  The 500 here therefore has a
    different cause from the one
    :func:`test_get_tweets_response_validation_rejects_incomplete_row` asserts,
    where ``.all()`` succeeded and serialization is what failed.
    """
    override_get_db(mock_db)
    chain = mock_db.query.return_value.offset.return_value.limit.return_value
    chain.all.side_effect = RuntimeError(RESULT_READ_FAILURE_MESSAGE)

    response = client_no_raise.get(TWEETS_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.text == SERVER_ERROR_BODY
    assert response.headers["content-type"].startswith(
        SERVER_ERROR_CONTENT_TYPE
    )


# GET /tweets/{tweet_id} -- one failure, asserted as an exception through
# `client` and as a status through `client_no_raise`.


def test_get_tweet_by_id_raises_attribute_error(
    client, mock_db, override_get_db
):
    override_get_db(mock_db)

    with pytest.raises(AttributeError) as excinfo:
        client.get(TWEET_DETAIL_PATH)

    assert MISSING_SCHEMA_ATTRIBUTE in str(excinfo.value)
    assert "Tweet" in str(excinfo.value)
    _assert_queried_the_tweet_model(mock_db)


def test_get_tweet_by_id_returns_500(
    client_no_raise, mock_db, override_get_db
):
    override_get_db(mock_db)

    response = client_no_raise.get(TWEET_DETAIL_PATH)

    assert response.status_code == SERVER_ERROR_STATUS


def test_get_tweet_by_id_404_branch_is_unreachable(
    client_no_raise, mock_db, override_get_db
):
    override_get_db(mock_db)
    _program_single_row(mock_db, None)

    response = client_no_raise.get(TWEET_DETAIL_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.status_code != UNREACHABLE_NOT_FOUND_STATUS
    _assert_queried_the_tweet_model(mock_db)
    mock_db.query.return_value.filter.assert_not_called()
    mock_db.query.return_value.filter.return_value.first.assert_not_called()


def test_get_tweet_by_id_queries_the_tweet_model(
    client_no_raise, mock_db, override_get_db
):
    """The detail handler passes ``Tweet`` to ``db.query`` before it fails.

    Line 18 evaluates ``db.query(Tweet)`` first and ``Tweet.id == tweet_id``
    second, so the query is issued with the model and only then does the
    attribute read end the request.  Asserting the argument is what
    distinguishes that from a handler that queried something else.
    """
    override_get_db(mock_db)

    response = client_no_raise.get(TWEET_DETAIL_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    mock_db.query.assert_called_once_with(Tweet)


# POST /tweets/{tweet_id}/responses -- fails at the same query, one line later.


def test_generate_response_raises_attribute_error(
    client, mock_db, override_get_db
):
    override_get_db(mock_db)

    with pytest.raises(AttributeError) as excinfo:
        client.post(TWEET_RESPONSES_PATH)

    assert MISSING_SCHEMA_ATTRIBUTE in str(excinfo.value)
    assert "Tweet" in str(excinfo.value)
    _assert_queried_the_tweet_model(mock_db)


def test_generate_response_returns_500(
    client_no_raise, mock_db, override_get_db
):
    override_get_db(mock_db)

    response = client_no_raise.post(TWEET_RESPONSES_PATH)

    assert response.status_code == SERVER_ERROR_STATUS


def test_generate_response_never_reaches_llm_service(
    client, mock_db, override_get_db
):
    override_get_db(mock_db)

    with pytest.raises(AttributeError):
        client.post(TWEET_RESPONSES_PATH)

    _assert_queried_the_tweet_model(mock_db)
    mock_db.query.return_value.filter.assert_not_called()
    mock_db.query.return_value.filter.return_value.first.assert_not_called()


def test_generate_response_queries_the_tweet_model(
    client_no_raise, mock_db, override_get_db
):
    """The responses handler passes ``Tweet`` to ``db.query`` before it fails.

    Line 27 is the same query line 18 makes, so the model reaches the injected
    database on this operation too -- and it is the only argument this endpoint
    ever supplies to it, since nothing after the query executes.
    """
    override_get_db(mock_db)

    response = client_no_raise.post(TWEET_RESPONSES_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    mock_db.query.assert_called_once_with(Tweet)


# Recorded gaps.  Each asserts an absence; none adds a route, a model or a
# fixture to create the subject it reports as missing.


@pytest.mark.parametrize("method, path", IMPLEMENTED_OPERATIONS)
def test_no_implemented_endpoint_accepts_a_request_body(
    integration_app, method, path
):
    operation = integration_app.openapi()["paths"][path][method]

    assert "requestBody" not in operation


def test_dependency_overrides_map_is_empty_at_test_start(integration_app):
    assert integration_app.dependency_overrides == {}


def _assert_queried_the_tweet_model(mock_db):
    """Assert the handler opened exactly one query, against ``Tweet`` itself.

    A ``MagicMock`` answers ``query(anything)`` with the same child, so every
    assertion further down a programmed chain holds no matter which model the
    handler asked for.  This is the oracle that closes that hole: the argument
    is compared by identity against the class ``app/schema/tweet.py`` declares,
    so a handler that queried a different model -- or queried twice -- is
    reported here rather than passing silently.
    """
    mock_db.query.assert_called_once_with(QUERY_MODEL)
    assert mock_db.query.call_args[0][0] is QUERY_MODEL
    assert mock_db.query.call_args[1] == {}


def _validation_details(response):
    """Return the ``detail`` list of a ``422`` body, asserting its envelope.

    fastapi answers a query-parameter validation failure with an object whose
    only key is ``detail`` and whose value is a list of per-parameter records.
    Both facts are asserted here, so a caller reading the records cannot be
    handed something of another shape.
    """
    body = response.json()

    assert tuple(body) == ("detail",)
    details = body["detail"]
    assert isinstance(details, list)
    return details


def test_get_tweets_queries_the_tweet_schema_model(
    client, mock_db, override_get_db
):
    """The collection handler queries the pydantic ``Tweet`` class itself.

    Line 13 opens with ``db.query(Tweet)``, where ``Tweet`` is the name line 5
    imports from ``app.schema.tweet``.  It is the same object this module
    imports, so the assertion is identity rather than a name comparison, and it
    is the one assertion in this suite that a handler querying some other model
    could not survive.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    _assert_queried_the_tweet_model(mock_db)


@pytest.mark.parametrize("parameter, value", MALFORMED_QUERY_VALUES)
def test_get_tweets_rejects_a_non_integer_query_value(
    client, mock_db, override_get_db, parameter, value
):
    """A value that cannot be coerced to ``int`` is refused with ``422``.

    The whole body is asserted, not only the status: ``detail`` carries exactly
    one record, and that record names the location ``["query", <parameter>]``
    together with pydantic v1's own message and error type.  Reading all three
    is what makes the oracle the *parameter that failed* rather than "some
    validation failed somewhere".

    The default ``client`` is used deliberately.  Validation happens in the
    framework rather than in a handler, so nothing raises and there is no
    server exception for ``client_no_raise`` to convert.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH, params={parameter: value})

    assert response.status_code == UNPROCESSABLE_ENTITY_STATUS
    details = _validation_details(response)
    assert len(details) == 1
    assert details[0] == {
        "loc": ["query", parameter],
        "msg": INTEGER_VALIDATION_MESSAGE,
        "type": INTEGER_VALIDATION_TYPE,
    }


@pytest.mark.parametrize("parameter, value", MALFORMED_QUERY_VALUES)
def test_get_tweets_does_not_reach_the_handler_on_a_rejected_query_value(
    client, mock_db, override_get_db, parameter, value
):
    """A rejected query value stops the request before the handler body runs.

    The injected database is programmed with a result set that would have been
    served successfully, so the ``422`` is not a symptom of the mock: the
    handler simply never opens a query, which is the difference between a
    framework rejection and a handler-level one.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [make_tweet()])

    response = client.get(TWEETS_PATH, params={parameter: value})

    assert response.status_code == UNPROCESSABLE_ENTITY_STATUS
    mock_db.query.assert_not_called()


def test_get_tweets_reports_both_invalid_query_values_in_declaration_order(
    client, mock_db, override_get_db
):
    """Two malformed values yield two records, ``skip`` before ``limit``.

    Validation does not stop at the first failure, and the records follow the
    order the parameters are declared in on line 12 rather than the order the
    query string presents them in -- so ``limit`` is sent first here and is
    still reported second.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(
        TWEETS_PATH, params={"limit": "def", "skip": "abc"}
    )

    assert response.status_code == UNPROCESSABLE_ENTITY_STATUS
    details = _validation_details(response)
    assert [record["loc"] for record in details] == [
        ["query", "skip"],
        ["query", "limit"],
    ]
    assert [record["type"] for record in details] == [
        INTEGER_VALIDATION_TYPE,
        INTEGER_VALIDATION_TYPE,
    ]
    mock_db.query.assert_not_called()


@pytest.mark.parametrize(
    "params, expected_offset, expected_limit", UNCONSTRAINED_QUERY_VALUES
)
def test_get_tweets_accepts_an_unconstrained_pagination_value(
    client, mock_db, override_get_db, params, expected_offset, expected_limit
):
    """A negative ``skip`` and a zero ``limit`` are accepted and passed on.

    Line 12 declares the two parameters as plain ``int`` with no ``ge``, ``gt``
    or ``le``, so the validation boundary is the type and nothing else.  Both
    values reach the query unchanged, which is the divergence: a caller asking
    for a negative offset or a page of nothing is not refused.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH, params=params)

    assert response.status_code == OK_STATUS
    _assert_queried_the_tweet_model(mock_db)
    offset = mock_db.query.return_value.offset
    offset.assert_called_once_with(expected_offset)
    offset.return_value.limit.assert_called_once_with(expected_limit)

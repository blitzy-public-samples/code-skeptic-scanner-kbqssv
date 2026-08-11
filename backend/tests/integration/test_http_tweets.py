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
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
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

#: What the ``List[Tweet]`` response model reports for a row missing
#: :data:`OMITTED_REQUIRED_FIELD`, measured against fastapi 0.95.2 and pydantic
#: 1.10.13. ``serialize_response`` validates the handler's return value with
#: ``loc=("response",)`` prefixed, so the location names the response, the index
#: within the list, and the field -- which is what identifies *response*
#: validation as the cause rather than any of the other ways this endpoint
#: reaches a 500.
RESPONSE_VALIDATION_LOCATION = ("response", 0, OMITTED_REQUIRED_FIELD)

#: pydantic's code for an absent required field.
MISSING_FIELD_VALIDATION_TYPE = "value_error.missing"

#: Its human-readable half.
MISSING_FIELD_VALIDATION_MESSAGE = "field required"

#: Name of the model the failure is reported against. Compared by name rather
#: than by identity because fastapi clones the response model into its own
#: namespace -- the raised error names ``pydantic.main.Tweet``, not
#: ``app.schema.tweet.Tweet``.
RESPONSE_MODEL_NAME = "Tweet"

#: Failure types injected into the collection endpoint's query chain.
#: ``Exception`` is included: it is the type a bare
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

#: ``limit`` values of an unbounded magnitude, with the integer each reaches the
#: query as. Line 12 declares ``limit: int`` with no ``le``, so the ceiling is
#: the machine's rather than the endpoint's; the largest here is one above a
#: signed 32-bit maximum, which is the value an operator would expect a store to
#: refuse.
UNBOUNDED_MAGNITUDE_LIMITS = (
    pytest.param({"limit": 1000000000}, 1000000000, id="one-billion"),
    pytest.param({"limit": 2147483647}, 2147483647, id="signed-32-bit-maximum"),
    pytest.param({"limit": 2147483648}, 2147483648, id="above-signed-32-bit"),
)

#: Identifiers for the three-row mixed-validity result set. Only the middle row
#: violates the response model, and it is the ``content`` key that is missing --
#: the same omission :data:`OMITTED_REQUIRED_FIELD` names for the single-row case.
FIRST_VALID_ROW_ID = "good-1"
MALFORMED_ROW_ID = "bad-2"
LAST_VALID_ROW_ID = "good-3"

#: Where the response model reports the failure when the malformed row is second.
#: The index is the row's position in the emitted list, which is what makes the
#: *cause* locatable from the exception even though the response never is.
MALFORMED_ROW_VALIDATION_LOCATION = ("response", 1, OMITTED_REQUIRED_FIELD)

#: Every slice of the mixed-validity result set, with the status it answers and
#: the row identifiers it emits. A slice succeeds exactly when it excludes index
#: 1, so the valid rows are reachable only by a caller who already knows which
#: index is bad.
MALFORMED_ROW_SLICES = (
    pytest.param(
        {"skip": 0, "limit": 1}, OK_STATUS, [FIRST_VALID_ROW_ID], id="first-row-only"
    ),
    pytest.param({"skip": 1, "limit": 1}, SERVER_ERROR_STATUS, None, id="bad-row-only"),
    pytest.param(
        {"skip": 2, "limit": 1}, OK_STATUS, [LAST_VALID_ROW_ID], id="last-row-only"
    ),
    pytest.param(
        {"skip": 0, "limit": 2}, SERVER_ERROR_STATUS, None, id="spans-the-bad-row"
    ),
    pytest.param(
        {"skip": 0, "limit": 3},
        SERVER_ERROR_STATUS,
        None,
        id="spans-every-row",
    ),
)

#: Stored values the response model silently changes on the way out, with what it
#: emits. The first is a widening coercion and the second is destructive: pydantic
#: v1 builds an ``int`` from a ``float`` by truncation, so ``12.9`` becomes ``12``
#: and the fractional part is discarded rather than refused.
SILENTLY_ADJUSTED_VALUES = (
    pytest.param("likes_count", "777", 777, id="string-count-coerced"),
    pytest.param("retweets_count", 12.9, 12, id="float-count-truncated"),
    pytest.param("likes_count", True, 1, id="boolean-count-coerced"),
)

#: ``doubt_rating`` values outside the 0-1 range the design documents describe.
#: The field is declared ``float`` with no ``ge``/``le``, so each is emitted as
#: stored.
UNBOUNDED_DOUBT_RATINGS = (
    pytest.param(42.5, id="far-above-maximum"),
    pytest.param(-1.0, id="below-minimum"),
)

#: A key ``app/schema/tweet.py`` does not declare, and a value distinctive enough
#: to sweep the whole response body for.
UNDECLARED_ROW_KEY = "sentiment_score"
UNDECLARED_ROW_VALUE = "UNDECLARED_KEY_SENTINEL"

#: The two field names ``frontend/src/services/twitterService.ts`` declares and
#: the schema does not, with values distinctive enough to sweep for.
ID_SENTINEL_VALUE = "ID_FIELD_SENTINEL"
TEXT_SENTINEL_VALUE = "TEXT_FIELD_SENTINEL"

#: Length of the ``YYYY-MM-DD`` prefix of a serialized timestamp. Used to search
#: only the time portion for a ``-``, so the date's own separators are not
#: mistaken for a negative UTC offset.
TIMESTAMP_DATE_LENGTH = 10

#: A timestamp that carries an offset, and the string the model emits for it.
AWARE_TIMESTAMP_VALUE = datetime(
    2024, 2, 2, 0, 0, 0, tzinfo=timezone(timedelta(hours=2))
)
AWARE_SERIALIZED_TIMESTAMP = "2024-02-02T00:00:00+02:00"

#: Stored text and a stored URL that a naive consumer would treat as trusted.
#: Both cross the wire exactly as stored.
MARKUP_CONTENT = "<script>alert('xss')</script> <b>bold</b>"
SCRIPT_SCHEME_URL = "javascript:alert(1)"
HTTPS_MEDIA_URL = "https://example.invalid/media.png"

#: The content type every successful response on this surface carries. It is the
#: only control that keeps :data:`MARKUP_CONTENT` inert when the response is
#: navigated to directly, since no ``X-Content-Type-Options`` accompanies it --
#: see ``test_app_lifecycle.py``.
JSON_CONTENT_TYPE = "application/json"


def _program_collection_rows(mock_db, rows):
    chain = mock_db.query.return_value.offset.return_value.limit.return_value
    chain.all.return_value = rows
    return mock_db


def _program_sliced_collection(mock_db, rows):
    """Answer ``offset(skip).limit(limit).all()`` with the corresponding slice.

    :func:`_program_collection_rows` returns one fixed result whatever the
    pagination, which is what every other case here wants.  The malformed-row
    slice matrix needs the opposite: the pagination has to select, because the
    fact under test is *which* rows a given slice spans.
    """

    def _offset(skip):
        def _limit(limit):
            selected = mock_db.query.return_value.offset.return_value.limit
            page = MagicMock(name="page")
            start = skip if skip and skip > 0 else 0
            page.all.return_value = rows[start:start + limit]
            selected.return_value = page
            return page

        paged = MagicMock(name="paged")
        paged.limit.side_effect = _limit
        return paged

    mock_db.query.return_value.offset.side_effect = _offset
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


def test_get_tweets_response_validation_raises_for_incomplete_row(
    client, mock_db, override_get_db
):
    """A row missing ``content`` fails the response model, and that is the cause.

    The status a caller sees is a bare ``500``, and this endpoint reaches ``500``
    three other ways -- a failing ``db.query``, a failing terminal ``.all()``, and
    any exception at all, since the handler holds no ``try``. The cause is
    observable only in the exception, so it is asserted through the raising
    client: a pydantic :class:`ValidationError` against the response model, one
    entry located at ``("response", 0, "content")``, and a query chain that ran to
    completion -- so the handler obtained its result set and serialization is what
    rejected it.
    """
    override_get_db(mock_db)
    incomplete = make_tweet()
    del incomplete[OMITTED_REQUIRED_FIELD]
    chain = mock_db.query.return_value.offset.return_value.limit.return_value
    _program_collection_rows(mock_db, [incomplete])

    with pytest.raises(ValidationError) as excinfo:
        client.get(TWEETS_PATH)

    # Reported against the response model, named rather than identified: fastapi
    # clones it into its own namespace when it builds the response field.
    assert excinfo.value.model.__name__ == RESPONSE_MODEL_NAME

    errors = excinfo.value.errors()

    assert len(errors) == 1
    assert tuple(errors[0]["loc"]) == RESPONSE_VALIDATION_LOCATION
    assert errors[0]["type"] == MISSING_FIELD_VALIDATION_TYPE
    assert errors[0]["msg"] == MISSING_FIELD_VALIDATION_MESSAGE

    # The chain completed, so the row reached the response model. This is what
    # separates this 500 from the query-failure and result-read-failure ones,
    # where `.all()` never returned.
    _assert_queried_the_tweet_model(mock_db)
    chain.all.assert_called_once_with()


def test_get_tweets_response_validation_rejects_incomplete_row(
    client_no_raise, mock_db, override_get_db
):
    """The same failure answers ``500`` through a client that reports.

    The body is starlette's own server-error text under ``text/plain`` rather than
    a JSON array, so the ``List[Tweet]`` response model produced nothing, and the
    completed query chain shows it was nonetheless *reached* -- the pair that
    distinguishes this 500 from the two where the chain failed first.
    """
    override_get_db(mock_db)
    incomplete = make_tweet()
    del incomplete[OMITTED_REQUIRED_FIELD]
    chain = mock_db.query.return_value.offset.return_value.limit.return_value
    _program_collection_rows(mock_db, [incomplete])

    response = client_no_raise.get(TWEETS_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.text == SERVER_ERROR_BODY
    assert response.headers["content-type"].startswith(SERVER_ERROR_CONTENT_TYPE)
    _assert_queried_the_tweet_model(mock_db)
    chain.all.assert_called_once_with()


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


# --------------------------------------------------------------------------- #
# The three operations with ``Depends(get_db)`` left in place.
#
# Every case above installs a stand-in through ``override_get_db``, so the
# dependency the application actually declares is never resolved.  These cases
# resolve it: ``app.db.firestore.get_db`` runs, and the only thing replaced is the
# ``Client`` class it constructs, through the ``firestore_client_constructor``
# fixture whose stand-in is specified against ``google.cloud.firestore.Client``.
# The endpoint therefore meets the attribute surface a real Firestore client has,
# which is the disposition ``frontend/src/test-utils/handlers.ts`` models in its
# configured-base, unoverridden column.
# --------------------------------------------------------------------------- #

#: The attribute the SQLAlchemy-shaped handlers read off the injected object and
#: that a Firestore client does not carry.
MISSING_CLIENT_ATTRIBUTE = "query"


def test_a_firestore_client_declares_no_query_attribute():
    """The production fact every case below rests on.

    ``app/api/routes/tweets.py`` was written against a SQLAlchemy ``Session`` and
    is wired to ``app/db/firestore.py``, whose client has no ``query``.  Asserted
    against the real class, so the stand-in the fixture builds is faithful by
    construction rather than by assumption.
    """
    from google.cloud.firestore import Client as FirestoreClient

    assert hasattr(FirestoreClient, MISSING_CLIENT_ATTRIBUTE) is False


def test_get_tweets_resolves_the_declared_dependency(
    client_no_raise, firestore_client_constructor, integration_app
):
    """With no override installed, the request builds a real Firestore client.

    The empty override map and the recorded constructor call together are what
    show the dependency was resolved rather than substituted, which is the
    property that makes the status below an oracle.
    """
    assert integration_app.dependency_overrides == {}

    client_no_raise.get(TWEETS_PATH)

    firestore_client_constructor.assert_called_once_with(
        project=importlib.import_module("app.core.config").Settings().PROJECT_ID
    )


def test_get_tweets_raises_attribute_error_without_an_override(
    client, firestore_client_constructor
):
    """A valid collection request fails on ``db.query`` before any Firestore call."""
    with pytest.raises(AttributeError) as excinfo:
        client.get(TWEETS_PATH)

    assert MISSING_CLIENT_ATTRIBUTE in str(excinfo.value)


def test_get_tweets_returns_500_without_an_override(
    client_no_raise, firestore_client_constructor
):
    """The same failure reported as a response: ``500`` and the plain-text body.

    This is the value ``configuredBaseBackendHandlers()`` answers for a valid
    ``GET /tweets`` while its ``dependencyOverridden`` option is unset.
    """
    response = client_no_raise.get(TWEETS_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.text == SERVER_ERROR_BODY
    assert response.headers["content-type"].startswith(SERVER_ERROR_CONTENT_TYPE)


def test_get_tweets_returns_500_for_the_pagination_callers_send(
    client_no_raise, firestore_client_constructor
):
    """The disposition does not depend on the query the callers emit.

    ``fetchTweets(page, limit)`` sends ``page`` and ``limit``; ``page`` is not
    declared and is ignored, and a coercible ``limit`` passes validation, so the
    request reaches the endpoint and fails there.
    """
    response = client_no_raise.get(
        TWEETS_PATH, params={"page": 2, "limit": EXPLICIT_LIMIT}
    )

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.text == SERVER_ERROR_BODY


@pytest.mark.parametrize("parameter, value", MALFORMED_QUERY_VALUES)
def test_get_tweets_rejects_a_malformed_value_before_the_dependency_fails(
    client_no_raise, firestore_client_constructor, parameter, value
):
    """Coercion precedes endpoint execution, override or no override.

    A ``422`` here rather than a ``500`` is what fixes the stage order the mock
    models: validation of the declared parameters happens before the handler body,
    so the dependency's own failure is never reached.
    """
    response = client_no_raise.get(TWEETS_PATH, params={parameter: value})

    assert response.status_code == UNPROCESSABLE_ENTITY_STATUS
    assert [record["loc"] for record in _validation_details(response)] == [
        ["query", parameter]
    ]


def test_get_tweet_by_id_returns_500_without_an_override(
    client_no_raise, firestore_client_constructor
):
    """The detail route answers ``500`` with the dependency in place.

    It fails one step earlier than it does under a SQLAlchemy-shaped stand-in --
    on ``db.query`` rather than on ``Tweet.id`` -- and the response is identical,
    so the frontend mock answers one value for both dispositions.
    """
    response = client_no_raise.get(TWEET_DETAIL_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.text == SERVER_ERROR_BODY
    assert response.headers["content-type"].startswith(SERVER_ERROR_CONTENT_TYPE)


def test_get_tweet_by_id_raises_on_the_client_attribute_without_an_override(
    client, firestore_client_constructor
):
    """Naming the attribute distinguishes this failure from the ``Tweet.id`` one."""
    with pytest.raises(AttributeError) as excinfo:
        client.get(TWEET_DETAIL_PATH)

    assert MISSING_CLIENT_ATTRIBUTE in str(excinfo.value)


def test_generate_response_returns_500_without_an_override(
    client_no_raise, firestore_client_constructor
):
    """The responses route answers ``500`` with the dependency in place."""
    response = client_no_raise.post(TWEET_RESPONSES_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.text == SERVER_ERROR_BODY
    assert response.headers["content-type"].startswith(SERVER_ERROR_CONTENT_TYPE)


def test_generate_response_raises_on_the_client_attribute_without_an_override(
    client, firestore_client_constructor
):
    """The same attribute read ends the responses operation."""
    with pytest.raises(AttributeError) as excinfo:
        client.post(TWEET_RESPONSES_PATH)

    assert MISSING_CLIENT_ATTRIBUTE in str(excinfo.value)


# --------------------------------------------------------------------------- #
# The full coercion domain of the two declared ``int`` parameters.
#
# pydantic v1 coerces a query value by calling ``int(value)``, so the domain is
# CPython's own base-10 literal grammar rather than ASCII digits: an optional
# sign, one or more Unicode decimal digits, and single ``_`` separators strictly
# between digits.  ``frontend/src/test-utils/handlers.ts`` models this endpoint,
# so its ``INTEGER_VALUE`` grammar is held to the same domain by the cases below
# and by their counterparts in ``handlers.test.ts``.
# --------------------------------------------------------------------------- #

#: Values ``int()`` accepts beyond the plain ASCII digits every caller emits, each
#: with the integer it coerces to.
UNCONVENTIONAL_INTEGER_VALUES = (
    pytest.param("1_0", 10, id="underscore-separated"),
    pytest.param("1_0_0", 100, id="two-underscore-groups"),
    pytest.param("+1_0", 10, id="signed-underscore-separated"),
    pytest.param("\u0661\u0660", 10, id="arabic-indic-digits"),
    pytest.param("\uff11\uff10", 10, id="fullwidth-digits"),
    pytest.param("\u06f1\u06f0", 10, id="extended-arabic-indic-digits"),
    pytest.param("\u0f21\u0f20", 10, id="tibetan-digits"),
    pytest.param("\u0661\u0031", 11, id="mixed-script-digits"),
    pytest.param("\uff11_\uff10", 10, id="fullwidth-underscore-separated"),
)

#: Values that resemble the ones above and that ``int()`` refuses: an underscore
#: outside a digit pair, and a digit-like character outside category ``Nd``.
REFUSED_INTEGER_LOOKALIKES = (
    pytest.param("_10", id="leading-underscore"),
    pytest.param("10_", id="trailing-underscore"),
    pytest.param("1__0", id="doubled-underscore"),
    pytest.param("+_10", id="underscore-after-sign"),
    pytest.param("\u2070", id="superscript-zero"),
    pytest.param("\u00b2", id="superscript-two"),
    pytest.param("\u00bd", id="vulgar-fraction-half"),
)


@pytest.mark.parametrize("value, coerced", UNCONVENTIONAL_INTEGER_VALUES)
def test_get_tweets_coerces_an_unconventional_integer_limit(
    client, mock_db, override_get_db, value, coerced
):
    """``limit`` is accepted and reaches the query as the integer it denotes."""
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH, params={"limit": value})

    assert response.status_code == OK_STATUS
    offset = mock_db.query.return_value.offset
    offset.return_value.limit.assert_called_once_with(coerced)


@pytest.mark.parametrize("value, coerced", UNCONVENTIONAL_INTEGER_VALUES)
def test_get_tweets_coerces_an_unconventional_integer_skip(
    client, mock_db, override_get_db, value, coerced
):
    """The same domain governs ``skip``; neither parameter narrows it."""
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH, params={"skip": value})

    assert response.status_code == OK_STATUS
    mock_db.query.return_value.offset.assert_called_once_with(coerced)


@pytest.mark.parametrize("value", REFUSED_INTEGER_LOOKALIKES)
def test_get_tweets_refuses_an_integer_lookalike(
    client_no_raise, mock_db, override_get_db, value
):
    """A value ``int()`` refuses is a ``422`` and never reaches the handler."""
    override_get_db(mock_db)

    response = client_no_raise.get(TWEETS_PATH, params={"limit": value})

    assert response.status_code == UNPROCESSABLE_ENTITY_STATUS
    assert [record["loc"] for record in _validation_details(response)] == [
        ["query", "limit"]
    ]
    mock_db.query.assert_not_called()


# --------------------------------------------------------------------------- #
# One malformed row makes the WHOLE collection unavailable                     #
# --------------------------------------------------------------------------- #
# ``test_get_tweets_response_validation_raises_for_incomplete_row`` above pins
# the cause for a single-row result.  These cases pin the *blast radius*, which
# is a different fact: the handler returns a ``list`` and the response model is
# ``List[Tweet]``, so fastapi validates the whole list as one value.  One row
# that fails therefore takes every valid row with it -- there is no partial
# result, no skip-bad-record and no per-record error envelope, and the caller
# receives an opaque ``500`` that cannot be distinguished from a broken server.


@pytest.fixture
def mixed_validity_rows():
    """Three rows of which only the middle one violates the response model.

    The valid rows are named, so an assertion can show *which* rows were
    reachable rather than only how many.
    """
    malformed = make_tweet(tweet_id=MALFORMED_ROW_ID)
    del malformed[OMITTED_REQUIRED_FIELD]
    return [
        make_tweet(tweet_id=FIRST_VALID_ROW_ID),
        malformed,
        make_tweet(tweet_id=LAST_VALID_ROW_ID),
    ]


def test_get_tweets_one_malformed_row_fails_the_whole_collection(
    client, mock_db, override_get_db, mixed_validity_rows
):
    """The response model rejects the list, naming the offending row's index.

    ``loc`` carries the index, so the *cause* is precisely locatable from the
    exception -- and only from the exception, because nothing in the HTTP
    response says which row it was.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, mixed_validity_rows)

    with pytest.raises(ValidationError) as excinfo:
        client.get(TWEETS_PATH)

    assert excinfo.value.model.__name__ == RESPONSE_MODEL_NAME
    assert [error["loc"] for error in excinfo.value.errors()] == [
        MALFORMED_ROW_VALIDATION_LOCATION
    ]
    assert [error["type"] for error in excinfo.value.errors()] == [
        MISSING_FIELD_VALIDATION_TYPE
    ]


def test_get_tweets_one_malformed_row_returns_500_with_no_partial_body(
    client_no_raise, mock_db, override_get_db, mixed_validity_rows
):
    """What the caller receives carries neither the valid rows nor the reason.

    The body is the bare ``text/plain`` ``Internal Server Error`` -- so a client
    cannot tell "the server is broken" from "one stored record is malformed",
    and neither valid row is reachable through this request at all.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, mixed_validity_rows)

    response = client_no_raise.get(TWEETS_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.text == SERVER_ERROR_BODY
    assert response.headers["content-type"].startswith(SERVER_ERROR_CONTENT_TYPE)
    for row_id in (FIRST_VALID_ROW_ID, LAST_VALID_ROW_ID, MALFORMED_ROW_ID):
        assert row_id not in response.text


@pytest.mark.parametrize(
    "params, expected_status, expected_ids", MALFORMED_ROW_SLICES
)
def test_get_tweets_slice_outcome_depends_on_whether_it_spans_the_bad_row(
    client_no_raise,
    mock_db,
    override_get_db,
    mixed_validity_rows,
    params,
    expected_status,
    expected_ids,
):
    """A slice succeeds exactly when it excludes the malformed row.

    This is the operational consequence: the valid rows are still *retrievable*,
    but only by a caller who already knows the bad row's index -- which is the
    one thing the ``500`` does not tell them.  The pagination arguments are the
    same unconstrained ``skip``/``limit`` pair every other case here uses; no
    per-record handling exists to make the difference.
    """
    override_get_db(mock_db)
    _program_sliced_collection(mock_db, mixed_validity_rows)

    response = client_no_raise.get(TWEETS_PATH, params=params)

    assert response.status_code == expected_status
    if expected_status == OK_STATUS:
        assert [record["tweet_id"] for record in response.json()] == expected_ids
    else:
        assert response.text == SERVER_ERROR_BODY


# --------------------------------------------------------------------------- #
# What the response model does to a row's values on the way out                #
# --------------------------------------------------------------------------- #
# Serialization is not a pass-through.  ``List[Tweet]`` is a validating model, so
# every emitted row is the result of pydantic v1 coercion against
# ``app/schema/tweet.py`` rather than the stored row itself.  Three classes of
# change happen silently and none is logged: a value is COERCED, a value is
# TRUNCATED, and an undeclared key is DROPPED.  A fourth is an absence: no field
# declares a range, so a ``doubt_rating`` far outside 0-1 is emitted unchanged.


@pytest.mark.parametrize(
    "field_name, stored, emitted", SILENTLY_ADJUSTED_VALUES
)
def test_get_tweets_adjusts_a_stored_value_without_saying_so(
    client, mock_db, override_get_db, field_name, stored, emitted
):
    """A stored value is coerced or truncated on the way out, with no warning.

    ``retweets_count`` is the destructive case: ``int(12.9)`` is ``12``, so a
    real value is discarded rather than refused.  Asserted through the emitted
    JSON rather than the model, because the emitted JSON is what a client reads.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [make_tweet(**{field_name: stored})])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    record = response.json()[0]
    assert record[field_name] == emitted
    assert isinstance(record[field_name], type(emitted))


@pytest.mark.parametrize("doubt_rating", UNBOUNDED_DOUBT_RATINGS)
def test_get_tweets_emits_a_doubt_rating_outside_its_nominal_range(
    client, mock_db, override_get_db, doubt_rating
):
    """``doubt_rating`` is a bare ``float`` -- nothing constrains it to 0-1.

    The design documents describe a rating and ``DOUBT_RATING_THRESHOLD`` is
    ``0.7``, but the schema declares no bound and no production code compares
    against that threshold, so a negative or many-times-maximum rating travels
    to the client intact.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [make_tweet(doubt_rating=doubt_rating)])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    assert response.json()[0]["doubt_rating"] == doubt_rating


def test_get_tweets_drops_an_undeclared_key_from_the_emitted_row(
    client, mock_db, override_get_db
):
    """A key the schema does not declare is discarded, not rejected and not echoed."""
    override_get_db(mock_db)
    _program_collection_rows(
        mock_db, [make_tweet(**{UNDECLARED_ROW_KEY: UNDECLARED_ROW_VALUE})]
    )

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    assert UNDECLARED_ROW_KEY not in response.json()[0]
    assert UNDECLARED_ROW_VALUE not in response.text


def test_get_tweets_strips_the_field_names_the_client_expects(
    client, mock_db, override_get_db
):
    """``id`` and ``text`` are removed even when the stored row carries them.

    ``frontend/src/services/twitterService.ts`` declares a tweet with ``id`` and
    ``text``.  Neither is declared by ``app/schema/tweet.py``, and the response
    model emits only declared fields -- so those two names can never reach the
    browser, whatever is stored.  The sentinel *values* are swept for as well as
    the key names, because a value surviving under a different key would be a
    different outcome.
    """
    override_get_db(mock_db)
    _program_collection_rows(
        mock_db,
        [make_tweet(id=ID_SENTINEL_VALUE, text=TEXT_SENTINEL_VALUE)],
    )

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    assert tuple(response.json()[0]) == TWEET_FIELD_NAMES
    for absent in (
        ID_SENTINEL_VALUE,
        TEXT_SENTINEL_VALUE,
        '"id"',
        '"text"',
    ):
        assert absent not in response.text


# --------------------------------------------------------------------------- #
# How the one datetime field crosses the wire                                  #
# --------------------------------------------------------------------------- #


def test_get_tweets_emits_a_naive_timestamp_with_no_timezone_designator(
    client, mock_db, override_get_db
):
    """The emitted timestamp names no zone, so a client must assume one.

    ``timestamp`` is ``datetime`` and the fixture's value is naive, so pydantic's
    ISO-8601 rendering carries neither ``Z`` nor an offset.  Per ES2015 a
    date-time string without a designator is parsed by ``new Date()`` as *local*
    time, so the instant a browser reconstructs depends on the reader's zone --
    which is the latent half of the ``z.date()`` mismatch that
    ``frontend/src/schema/tweetSchema.test.ts`` pins from the client side.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [make_tweet()])

    response = client.get(TWEETS_PATH)

    emitted = response.json()[0]["timestamp"]

    assert emitted == SERIALIZED_TIMESTAMP
    assert not emitted.endswith("Z")
    assert "+" not in emitted
    assert emitted[TIMESTAMP_DATE_LENGTH:].count("-") == 0


def test_get_tweets_preserves_the_offset_of_an_aware_timestamp(
    client, mock_db, override_get_db
):
    """An aware value keeps its offset, so the absence above is the value's, not the model's.

    The same field emits ``+02:00`` when the stored value carries it.  So a
    deployment cannot rely on the emitted form being zone-free either: the two
    renderings differ by what was stored, and nothing normalises them.
    """
    override_get_db(mock_db)
    _program_collection_rows(
        mock_db, [make_tweet(timestamp=AWARE_TIMESTAMP_VALUE)]
    )

    response = client.get(TWEETS_PATH)

    assert response.json()[0]["timestamp"] == AWARE_SERIALIZED_TIMESTAMP


# --------------------------------------------------------------------------- #
# Stored text crosses the wire verbatim                                        #
# --------------------------------------------------------------------------- #


def test_get_tweets_emits_stored_markup_without_escaping_it(
    client, mock_db, override_get_db
):
    """Markup in ``content`` is emitted as the characters that were stored.

    Correct for a JSON API -- JSON escaping is not HTML escaping -- and recorded
    because it makes every downstream consumer responsible for escaping on
    output.  The count of ``&lt;`` is asserted rather than merely the presence of
    ``<``, so "unescaped" is measured rather than assumed.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [make_tweet(content=MARKUP_CONTENT)])

    response = client.get(TWEETS_PATH)

    assert response.json()[0]["content"] == MARKUP_CONTENT
    assert response.text.count("&lt;") == 0
    assert response.headers["content-type"] == JSON_CONTENT_TYPE


def test_get_tweets_emits_a_javascript_url_with_no_scheme_validation(
    client, mock_db, override_get_db
):
    """``media_urls`` is ``List[str]`` -- any scheme at all is emitted intact.

    Nothing here validates a URL, so a ``javascript:`` entry reaches the client
    exactly as stored.  Inert as long as no consumer binds it to an ``href`` or
    ``src``; recorded because the schema offers no defence if one ever does.
    """
    override_get_db(mock_db)
    _program_collection_rows(
        mock_db, [make_tweet(media_urls=[SCRIPT_SCHEME_URL, HTTPS_MEDIA_URL])]
    )

    response = client.get(TWEETS_PATH)

    assert response.json()[0]["media_urls"] == [SCRIPT_SCHEME_URL, HTTPS_MEDIA_URL]
    assert SCRIPT_SCHEME_URL in response.text


@pytest.mark.parametrize("params, expected_limit", UNBOUNDED_MAGNITUDE_LIMITS)
def test_get_tweets_accepts_a_limit_of_any_magnitude(
    client, mock_db, override_get_db, params, expected_limit
):
    """No maximum is declared, so a caller may ask for an unbounded page.

    The companion to ``test_get_tweets_accepts_an_unconstrained_pagination_value``
    above, which covers sign and zero: this covers magnitude, up to and beyond a
    signed 32-bit maximum.  Every value reaches the query unchanged, so the only
    thing standing between a caller and a whole-collection read is the store.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH, params=params)

    assert response.status_code == OK_STATUS
    offset = mock_db.query.return_value.offset
    offset.return_value.limit.assert_called_once_with(expected_limit)

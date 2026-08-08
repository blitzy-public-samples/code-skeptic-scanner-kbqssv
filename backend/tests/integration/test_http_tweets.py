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

Two consequences are asserted here as the behaviour production exhibits:

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

The wiring of the application object, its middleware and its lifecycle
handlers belongs to ``backend/tests/integration/test_app_lifecycle.py``.  The
behaviour of ``app/db/firestore.py`` itself belongs to
``backend/tests/unit/test_db_firestore.py``; the injected stand-in here is a
``MagicMock`` and no test asserts anything about the real module.

Reasoning for asserting the unreachable 404 as a 500 rather than repairing the
handler: ``docs/testing/DECISION-LOG.md``.
"""

import pytest

from tests.factories import make_tweet

pytestmark = pytest.mark.integration


# Oracles.  Every value below is read from the subject module, from
# app/schema/tweet.py, or from the measured behaviour of the pinned stack.

#: Collection endpoint, ``@router.get('/tweets')`` at line 11.
TWEETS_PATH = "/tweets"

#: ``tweet_id`` used for both single-tweet paths.  Never resolved: the handler
#: raises before the value is compared against anything.
TWEET_ID = "1234567890"

#: Detail path, ``@router.get('/tweets/{tweet_id}')`` at line 16.
TWEET_DETAIL_PATH = "/tweets/{0}".format(TWEET_ID)

#: Responses path, ``@router.post('/tweets/{tweet_id}/responses')`` at line 23.
TWEET_RESPONSES_PATH = "/tweets/{0}/responses".format(TWEET_ID)

OK_STATUS = 200

#: Status a handler exception surfaces as through ``client_no_raise``.  Both
#: filtering handlers and a response-validation failure produce it.
SERVER_ERROR_STATUS = 500

#: Status the unreachable guard on lines 19-20 and 28-29 would have produced.
UNREACHABLE_NOT_FOUND_STATUS = 404

#: Declared default of the ``skip`` query parameter, line 12.
DEFAULT_SKIP = 0

#: Declared default of the ``limit`` query parameter, line 12.
DEFAULT_LIMIT = 100

#: Non-default pagination.  Each value differs from both declared defaults,
#: from the other, and from the length of any result set programmed here.
EXPLICIT_SKIP = 5

EXPLICIT_LIMIT = 2

#: The ten field names ``app/schema/tweet.py`` declares, in declaration order.
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

#: ``Tweet.timestamp`` is a ``datetime``; the factory supplies
#: ``datetime(2024, 1, 1, 0, 0, 0)``, which pydantic v1 serializes to this
#: naive ISO-8601 string.  The raw ``datetime`` never appears in a JSON body.
SERIALIZED_TIMESTAMP = "2024-01-01T00:00:00"

#: Field dropped to force a response-model validation failure.  Required, and
#: not the field any other assertion in this module varies.
OMITTED_REQUIRED_FIELD = "content"

#: Attribute named by the ``AttributeError`` both filtering handlers raise.
#: The full message is ``"type object 'Tweet' has no attribute 'id'"``.
MISSING_SCHEMA_ATTRIBUTE = "id"

#: Every path template the subject registers, as it appears in the OpenAPI
#: document.  The ``requestBody`` assertion covers all three.
IMPLEMENTED_OPERATIONS = (
    pytest.param("get", "/tweets", id="get-tweets"),
    pytest.param("get", "/tweets/{tweet_id}", id="get-tweet-by-id"),
    pytest.param(
        "post", "/tweets/{tweet_id}/responses", id="post-tweet-responses"
    ),
)


# Helpers.  Both program one link of the call chain the handler under test
# drives off the injected object; neither asserts anything.


def _program_collection_rows(mock_db, rows):
    """Program ``db.query(Tweet).offset(skip).limit(limit).all()`` on a mock.

    ``rows`` becomes the return value of the ``.all()`` at the end of the chain
    line 13 builds.  Returns the mock.
    """
    chain = mock_db.query.return_value.offset.return_value.limit.return_value
    chain.all.return_value = rows
    return mock_db


def _program_single_row(mock_db, row):
    """Program ``db.query(Tweet).filter(...).first()`` on a mock.

    ``row`` becomes the return value of the ``.first()`` at the end of the
    chain lines 18 and 27 build.  Neither handler reaches it -- the argument to
    ``.filter(...)`` raises first -- so this exists to prove that programming
    the guard's input does not change the outcome.  Returns the mock.
    """
    mock_db.query.return_value.filter.return_value.first.return_value = row
    return mock_db


# GET /tweets -- the collection endpoint, the one operation that succeeds.


def test_get_tweets_returns_serialized_tweet(client, mock_db, override_get_db):
    """One row is ``200`` and a one-element list carrying all ten fields.

    The handler's ``-> List[Tweet]`` annotation is the response model, so the
    body is the schema's serialization of the row rather than the row itself:
    the keys are exactly the ten declared field names, ``timestamp`` is an
    ISO-8601 string and the un-overridden ``quoted_tweet_id`` is JSON ``null``.
    """
    override_get_db(mock_db)
    expected = make_tweet()
    _program_collection_rows(mock_db, [expected])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
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
    """An empty result set is ``200`` and ``[]``.

    The handler has no branch for an empty collection, so nothing turns it into
    a 404 or an error.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    assert response.json() == []


def test_get_tweets_passes_pagination_to_query(
    client, mock_db, override_get_db
):
    """``skip`` and ``limit`` reach ``.offset()`` and ``.limit()`` unchanged.

    Both are query parameters.  ``.offset`` is called on the object
    ``db.query(...)`` returned and ``.limit`` on the object ``.offset(...)``
    returned, which is the order line 13 chains them in.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(
        TWEETS_PATH, params={"skip": EXPLICIT_SKIP, "limit": EXPLICIT_LIMIT}
    )

    assert response.status_code == OK_STATUS
    offset = mock_db.query.return_value.offset
    offset.assert_called_once_with(EXPLICIT_SKIP)
    offset.return_value.limit.assert_called_once_with(EXPLICIT_LIMIT)


def test_get_tweets_uses_default_pagination(client, mock_db, override_get_db):
    """Omitting both parameters applies the defaults ``0`` and ``100``.

    The defaults are those on line 12; no request header or body can supply
    them, so an empty query string is what exercises them.
    """
    override_get_db(mock_db)
    _program_collection_rows(mock_db, [])

    response = client.get(TWEETS_PATH)

    assert response.status_code == OK_STATUS
    offset = mock_db.query.return_value.offset
    offset.assert_called_once_with(DEFAULT_SKIP)
    offset.return_value.limit.assert_called_once_with(DEFAULT_LIMIT)


def test_get_tweets_response_validation_rejects_incomplete_row(
    client_no_raise, mock_db, override_get_db
):
    """A row missing a required field surfaces as ``500``.

    Dropping ``content`` leaves the row unable to satisfy the ``List[Tweet]``
    response model.  fastapi 0.95.2 lets the resulting pydantic
    ``ValidationError`` escape response serialization as an unhandled server
    exception, so the status is 500 rather than a 4xx.
    """
    override_get_db(mock_db)
    incomplete = make_tweet()
    del incomplete[OMITTED_REQUIRED_FIELD]
    _program_collection_rows(mock_db, [incomplete])

    response = client_no_raise.get(TWEETS_PATH)

    assert response.status_code == SERVER_ERROR_STATUS


# GET /tweets/{tweet_id} -- one failure, asserted as an exception through
# `client` and as a status through `client_no_raise`.


def test_get_tweet_by_id_raises_attribute_error(
    client, mock_db, override_get_db
):
    """The handler raises ``AttributeError`` naming the attribute ``id``.

    Line 18 evaluates ``Tweet.id == tweet_id`` to build the argument for
    ``.filter(...)``.  ``Tweet`` declares no ``id`` and pydantic v1 leaves none
    on the class, so the comparison raises.  The message is asserted so the
    oracle is this specific missing attribute rather than any
    ``AttributeError`` from anywhere in the request.
    """
    override_get_db(mock_db)

    with pytest.raises(AttributeError) as excinfo:
        client.get(TWEET_DETAIL_PATH)

    assert MISSING_SCHEMA_ATTRIBUTE in str(excinfo.value)
    assert "Tweet" in str(excinfo.value)


def test_get_tweet_by_id_returns_500(
    client_no_raise, mock_db, override_get_db
):
    """The same request answers ``500`` through a client that reports.

    This is the status a caller observes, and it is the divergence: the handler
    was written to answer 200 or 404 and answers neither.
    """
    override_get_db(mock_db)

    response = client_no_raise.get(TWEET_DETAIL_PATH)

    assert response.status_code == SERVER_ERROR_STATUS


def test_get_tweet_by_id_404_branch_is_unreachable(
    client_no_raise, mock_db, override_get_db
):
    """The ``404`` guard does not run even when given the input it exists for.

    ``.first()`` is programmed to return ``None``, which is exactly what lines
    19-20 test for.  The status is still ``500`` and never ``404``, because the
    ``AttributeError`` on line 18 is raised while building the argument to
    ``.filter(...)`` and therefore before any query result exists.  Neither
    ``.filter`` nor ``.first`` is reached.
    """
    override_get_db(mock_db)
    _program_single_row(mock_db, None)

    response = client_no_raise.get(TWEET_DETAIL_PATH)

    assert response.status_code == SERVER_ERROR_STATUS
    assert response.status_code != UNREACHABLE_NOT_FOUND_STATUS
    mock_db.query.return_value.filter.assert_not_called()
    mock_db.query.return_value.filter.return_value.first.assert_not_called()


# POST /tweets/{tweet_id}/responses -- fails at the same query, one line later.


def test_generate_response_raises_attribute_error(
    client, mock_db, override_get_db
):
    """The handler raises ``AttributeError`` naming the attribute ``id``.

    Line 27 is the same ``Tweet.id == tweet_id`` comparison line 18 makes, so
    the responses endpoint fails identically.  The request carries no body,
    because the operation declares no parameter that would accept one.
    """
    override_get_db(mock_db)

    with pytest.raises(AttributeError) as excinfo:
        client.post(TWEET_RESPONSES_PATH)

    assert MISSING_SCHEMA_ATTRIBUTE in str(excinfo.value)
    assert "Tweet" in str(excinfo.value)


def test_generate_response_returns_500(
    client_no_raise, mock_db, override_get_db
):
    """The same request answers ``500`` through a client that reports."""
    override_get_db(mock_db)

    response = client_no_raise.post(TWEET_RESPONSES_PATH)

    assert response.status_code == SERVER_ERROR_STATUS


def test_generate_response_never_reaches_llm_service(
    client, mock_db, override_get_db
):
    """Execution stops at the query, before the LLM boundary.

    The ``AttributeError`` from line 27 precedes ``LLMService()`` on line 31,
    so the endpoint's whole response-generation half is unreachable.  The
    oracle is the depth reached on the injected object: the raise happens while
    building the argument to ``.filter(...)``, so ``.filter`` is never called
    and ``.first`` -- the last step before the guard and the construction --
    is never called either.
    """
    override_get_db(mock_db)

    with pytest.raises(AttributeError):
        client.post(TWEET_RESPONSES_PATH)

    mock_db.query.assert_called_once()
    mock_db.query.return_value.filter.assert_not_called()
    mock_db.query.return_value.filter.return_value.first.assert_not_called()


# Recorded gaps.  Each asserts an absence; none adds a route, a model or a
# fixture to create the subject it reports as missing.


@pytest.mark.parametrize("method, path", IMPLEMENTED_OPERATIONS)
def test_no_implemented_endpoint_accepts_a_request_body(
    integration_app, method, path
):
    """No implemented operation declares a ``requestBody``.

    Read from the generated OpenAPI document, which is the contract a client
    consumes.  All three operations describe only ``parameters``, so an
    expectation of ``422`` for a malformed request body has no subject on this
    surface.
    """
    operation = integration_app.openapi()["paths"][path][method]

    assert "requestBody" not in operation


def test_dependency_overrides_map_is_empty_at_test_start(integration_app):
    """``app.dependency_overrides`` is empty when a test begins.

    Asserted without requesting ``override_get_db``, so what is observed is the
    state the autouse teardown in this folder's ``conftest.py`` leaves behind:
    no override installed by an earlier test survives into a later one,
    whichever order the two ran in.
    """
    assert integration_app.dependency_overrides == {}

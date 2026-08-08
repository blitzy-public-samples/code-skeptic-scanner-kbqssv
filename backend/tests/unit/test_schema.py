"""Unit suite for ``app/schema/tweet.py`` and ``app/schema/user.py``, and the
honesty gate for ``backend/tests/factories.py``.

``Tweet`` and ``User`` are the only schemas the repository declares.  ``Tweet``
declares ten fields, nine of them required; ``User`` declares five, all
required.  Both are pydantic v1 ``BaseModel`` subclasses, so
``__fields__[name].required`` is the required-versus-optional discriminator and
``__fields__`` is the declared field set.

What this module asserts
------------------------
Declared field sets
    That each model declares exactly the names its source file lists, in the
    order the source lists them.
Required-versus-optional split
    That ``Tweet`` requires exactly the nine fields declared without a default
    and that ``quoted_tweet_id``, declared ``Optional[str] = None``, is not one
    of them; and that every one of ``User``'s five fields is required.
Rejection of incomplete payloads
    That omitting any single required field raises
    ``pydantic.ValidationError`` reporting that field, and that such an error
    carries one ``value_error.missing`` entry whose ``loc`` names the field.
Type coercion other suites rely on
    That the two count fields accept an ``int`` unchanged and coerce a decimal
    string, that ``doubt_rating`` coerces an ``int`` to ``float``, and that
    ``timestamp`` accepts a ``datetime`` unchanged.
Names ``Tweet`` does not declare
    That ``id``, ``text``, ``user``, ``author``, ``created_at``,
    ``retweet_count`` and ``favorite_count`` are absent from ``Tweet``.
    Reading or supplying them is what produces the ``AttributeError`` at
    ``app/services/llm_service.py`` line 13, the nine-error
    ``ValidationError`` at ``app/services/twitter_service.py`` line 25, the
    eight-error ``ValidationError`` at ``app/tasks/tweet_processor.py``
    line 35, and the HTTP 500 from ``GET /tweets/{tweet_id}``, whose handler at
    ``app/api/routes/tweets.py`` line 18 filters on ``Tweet.id``.  Each is a
    divergence from the design documents, asserted here as the schema stands.
Unknown keyword arguments
    That ``Tweet.__config__.extra`` is ``Extra.ignore``, so a keyword naming no
    declared field is dropped without error rather than rejected.

The factory-honesty gate
------------------------
``backend/tests/factories.py`` publishes ``make_tweet(**overrides)`` as a
payload satisfying ``Tweet``.  The final section holds that claim to the
schema: that the payload carries exactly the ten declared keys, that
``Tweet(**make_tweet())`` constructs, that every value reaches the model with
its value and its type intact, that removing any one required key is rejected,
that an override reaches both the payload and the model, and that ``timestamp``
is a real ``datetime``.  A builder that no longer satisfies the schema, or a
schema that gains a field the builder does not supply, fails here.

Oracles
-------
Every expected name and value is a literal read from the two schema source
files, recorded in the constants below.  The parametrised matrices iterate
those constants, and the models under test contribute no case.

Shared infrastructure
---------------------
Test data comes from ``backend/tests/factories.py``, which imports no ``app``
module, performs no I/O and reads no clock.  The autouse credential neutraliser
and egress guard published by ``backend/tests/conftest.py`` apply to every test
here; neither is re-installed, and no test in this module reaches a network
boundary, a clock or a credential.  Both subjects import only ``pydantic``,
``typing`` and ``datetime``, so neither needs one of the shims that module
installs and no named fixture from its catalogue is used.  Neither subject
emits a log record or writes to a stream.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schema.tweet import Tweet
from app.schema.user import User
from tests.factories import make_tweet

pytestmark = pytest.mark.unit


# Oracles.  Every name and value below is read from ``app/schema/tweet.py`` or
# ``app/schema/user.py``; none is derived from the models under test.

#: The nine ``Tweet`` fields declared without a default, in source order.
TWEET_REQUIRED_FIELD_NAMES = (
    "tweet_id",
    "content",
    "user_id",
    "timestamp",
    "likes_count",
    "retweets_count",
    "doubt_rating",
    "ai_tools",
    "media_urls",
)

#: The one ``Tweet`` field carrying a declared default, which the source
#: declares ``Optional[str] = None``.
TWEET_OPTIONAL_FIELD_NAME = "quoted_tweet_id"

#: All ten fields ``Tweet`` declares, in source order.
TWEET_FIELD_NAMES = TWEET_REQUIRED_FIELD_NAMES + (TWEET_OPTIONAL_FIELD_NAME,)

#: The two ``Tweet`` fields declared ``int``.
TWEET_COUNT_FIELD_NAMES = ("likes_count", "retweets_count")

#: The five fields ``User`` declares, in source order.  None carries a default.
USER_FIELD_NAMES = (
    "user_id",
    "username",
    "display_name",
    "followers_count",
    "created_at",
)

#: Names production code reads off, or supplies to, a ``Tweet`` that the schema
#: does not declare.  ``app/services/twitter_service.py`` line 17 supplies the
#: first four; ``app/tasks/tweet_processor.py`` line 35 supplies six of the
#: seven; ``app/services/llm_service.py`` line 13 reads ``author`` and
#: ``created_at``; ``app/api/routes/tweets.py`` line 18 reads ``id``.
ABSENT_TWEET_FIELD_NAMES = (
    "id",
    "text",
    "user",
    "author",
    "created_at",
    "retweet_count",
    "favorite_count",
)

#: ``type`` pydantic v1 reports for a required field the payload omits.
MISSING_FIELD_ERROR_TYPE = "value_error.missing"

#: ``msg`` accompanying :data:`MISSING_FIELD_ERROR_TYPE`.
MISSING_FIELD_ERROR_MESSAGE = "field required"

#: ``created_at`` of the payload :func:`mock_user_payload` builds.  A literal
#: instant, so no assertion in this module reads a clock.
USER_CREATED_AT = datetime(2024, 1, 1, 0, 0, 0)

#: ``timestamp`` handed to :func:`test_tweet_timestamp_accepts_datetime`.
#: Distinct from the ``2024-01-01`` instant ``make_tweet`` supplies.
EXPLICIT_TIMESTAMP = datetime(2023, 6, 15, 12, 30, 45)

#: Value supplied to the count fields by the coercion assertions, as an ``int``
#: and as its decimal string.
COERCED_COUNT = 17

#: Value :func:`make_tweet` is asked to override ``likes_count`` with.
#: Different from the builder's default of 120.
OVERRIDDEN_LIKES_COUNT = 7


def _missing_field_names(error):
    """Return the set of field names ``error`` reports as missing.

    :param error: A ``pydantic.ValidationError``.
    :returns: The first element of the ``loc`` of every entry whose ``type`` is
        :data:`MISSING_FIELD_ERROR_TYPE`.
    """
    return {
        entry["loc"][0]
        for entry in error.errors()
        if entry["type"] == MISSING_FIELD_ERROR_TYPE
    }


@pytest.fixture
def mock_user_payload():
    """Return a freshly built payload carrying all five ``User`` fields.

    Every value is a literal, so two calls compare equal and a test that
    removes a key cannot affect another.  The repository declares no ``User``
    builder in ``backend/tests/factories.py``, and this payload is used by this
    module alone.
    """
    return {
        "user_id": "test_user",
        "username": "test_user",
        "display_name": "Test User",
        "followers_count": 3200,
        "created_at": USER_CREATED_AT,
    }


# --------------------------------------------------------------------------- #
# ``Tweet`` -- declared contract
# --------------------------------------------------------------------------- #


def test_tweet_declares_the_ten_documented_fields():
    """``Tweet.__fields__`` holds exactly :data:`TWEET_FIELD_NAMES`."""
    assert set(Tweet.__fields__) == set(TWEET_FIELD_NAMES)


def test_tweet_declares_its_fields_in_source_order():
    """``Tweet.__fields__`` is ordered as ``app/schema/tweet.py`` declares."""
    assert tuple(Tweet.__fields__) == TWEET_FIELD_NAMES


@pytest.mark.parametrize("field_name", TWEET_REQUIRED_FIELD_NAMES)
def test_tweet_field_is_required(field_name):
    """Each field declared without a default reports ``required``."""
    assert Tweet.__fields__[field_name].required is True


def test_tweet_requires_exactly_nine_fields():
    """No field outside :data:`TWEET_REQUIRED_FIELD_NAMES` is required."""
    required = {
        name for name, field in Tweet.__fields__.items() if field.required
    }

    assert required == set(TWEET_REQUIRED_FIELD_NAMES)


def test_tweet_quoted_tweet_id_is_not_required():
    """The one field carrying a declared default is optional."""
    assert Tweet.__fields__[TWEET_OPTIONAL_FIELD_NAME].required is False


def test_tweet_quoted_tweet_id_defaults_to_none_when_omitted():
    """A payload omitting ``quoted_tweet_id`` yields ``None`` on the model."""
    payload = make_tweet()
    payload.pop(TWEET_OPTIONAL_FIELD_NAME)

    assert Tweet(**payload).quoted_tweet_id is None


# --------------------------------------------------------------------------- #
# ``Tweet`` -- type coercion
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field_name", TWEET_COUNT_FIELD_NAMES)
def test_tweet_count_field_coerces_string_to_int(field_name):
    """A decimal string supplied for a count field becomes an ``int``."""
    tweet = Tweet(**make_tweet(**{field_name: str(COERCED_COUNT)}))
    value = getattr(tweet, field_name)

    assert value == COERCED_COUNT
    assert type(value) is int


@pytest.mark.parametrize("field_name", TWEET_COUNT_FIELD_NAMES)
def test_tweet_count_field_preserves_int(field_name):
    """An ``int`` supplied for a count field reaches the model unchanged."""
    tweet = Tweet(**make_tweet(**{field_name: COERCED_COUNT}))
    value = getattr(tweet, field_name)

    assert value == COERCED_COUNT
    assert type(value) is int


def test_tweet_doubt_rating_coerces_int_to_float():
    """An ``int`` supplied for ``doubt_rating`` becomes a ``float``."""
    tweet = Tweet(**make_tweet(doubt_rating=1))

    assert tweet.doubt_rating == 1.0
    assert type(tweet.doubt_rating) is float


def test_tweet_timestamp_accepts_datetime():
    """A ``datetime`` for ``timestamp`` reaches the model unchanged."""
    tweet = Tweet(**make_tweet(timestamp=EXPLICIT_TIMESTAMP))

    assert tweet.timestamp == EXPLICIT_TIMESTAMP
    assert type(tweet.timestamp) is datetime


# --------------------------------------------------------------------------- #
# ``Tweet`` -- names the schema does not declare
# --------------------------------------------------------------------------- #


def test_tweet_omits_the_names_production_assumes():
    """No name in :data:`ABSENT_TWEET_FIELD_NAMES` is a declared field.

    Reading or supplying these names is what produces the ``AttributeError``
    at ``app/services/llm_service.py`` line 13, the nine-error
    ``ValidationError`` at ``app/services/twitter_service.py`` line 25, the
    eight-error ``ValidationError`` at ``app/tasks/tweet_processor.py``
    line 35, and the HTTP 500 from ``GET /tweets/{tweet_id}``, whose handler at
    ``app/api/routes/tweets.py`` line 18 filters on ``Tweet.id``.  Each is a
    divergence from the design documents, asserted here as the schema stands.
    """
    assert set(ABSENT_TWEET_FIELD_NAMES).isdisjoint(Tweet.__fields__)


def test_tweet_ignores_unknown_keyword_arguments():
    """A keyword naming no declared field is dropped without error.

    ``Tweet.__config__.extra`` is ``Extra.ignore``, so the model constructs,
    no such name reaches the instance, and ``dict()`` carries exactly the ten
    declared fields.
    """
    unknown = {name: "ignored" for name in ABSENT_TWEET_FIELD_NAMES}

    tweet = Tweet(**make_tweet(), **unknown)
    accepted = {name for name in unknown if hasattr(tweet, name)}

    assert accepted == set()
    assert set(tweet.dict()) == set(TWEET_FIELD_NAMES)


# --------------------------------------------------------------------------- #
# ``User`` -- declared contract
# --------------------------------------------------------------------------- #


def test_user_declares_the_five_documented_fields():
    """``User.__fields__`` holds exactly :data:`USER_FIELD_NAMES`."""
    assert set(User.__fields__) == set(USER_FIELD_NAMES)


def test_user_declares_its_fields_in_source_order():
    """``User.__fields__`` is ordered as ``app/schema/user.py`` declares."""
    assert tuple(User.__fields__) == USER_FIELD_NAMES


def test_user_requires_every_declared_field():
    """Every one of the five declared ``User`` fields reports ``required``."""
    required = {
        name for name, field in User.__fields__.items() if field.required
    }

    assert required == set(USER_FIELD_NAMES)


def test_user_accepts_a_complete_payload(mock_user_payload):
    """The complete payload constructs, field value for field value."""
    user = User(**mock_user_payload)

    assert {
        name: getattr(user, name) for name in USER_FIELD_NAMES
    } == mock_user_payload


@pytest.mark.parametrize("field_name", USER_FIELD_NAMES)
def test_user_rejects_payload_missing_field(field_name, mock_user_payload):
    """Omitting any one ``User`` field is rejected, and only that field."""
    mock_user_payload.pop(field_name)

    with pytest.raises(ValidationError) as raised:
        User(**mock_user_payload)

    assert _missing_field_names(raised.value) == {field_name}


# --------------------------------------------------------------------------- #
# ``make_tweet`` -- the factory-honesty gate
# --------------------------------------------------------------------------- #


def test_make_tweet_supplies_exactly_the_schema_keys():
    """``make_tweet()`` returns exactly the ten keys ``Tweet`` declares."""
    assert set(make_tweet()) == set(Tweet.__fields__)


def test_make_tweet_payload_constructs_a_tweet():
    """``Tweet(**make_tweet())`` constructs."""
    assert isinstance(Tweet(**make_tweet()), Tweet)


@pytest.mark.parametrize("field_name", TWEET_FIELD_NAMES)
def test_make_tweet_value_survives_construction(field_name):
    """Each value ``make_tweet`` supplies equals what the model carries."""
    payload = make_tweet()

    assert getattr(Tweet(**payload), field_name) == payload[field_name]


@pytest.mark.parametrize("field_name", TWEET_FIELD_NAMES)
def test_make_tweet_value_type_survives_construction(field_name):
    """Each value ``make_tweet`` supplies reaches the model uncoerced."""
    payload = make_tweet()
    value = getattr(Tweet(**payload), field_name)

    assert type(value) is type(payload[field_name])


@pytest.mark.parametrize("field_name", TWEET_REQUIRED_FIELD_NAMES)
def test_tweet_rejects_payload_missing_required_field(field_name):
    """Removing any one required key from the payload is rejected."""
    payload = make_tweet()
    payload.pop(field_name)

    with pytest.raises(ValidationError) as raised:
        Tweet(**payload)

    assert _missing_field_names(raised.value) == {field_name}


def test_tweet_missing_field_error_reports_loc_type_and_message():
    """One omitted required field yields exactly one error entry naming it."""
    payload = make_tweet()
    payload.pop("content")

    with pytest.raises(ValidationError) as raised:
        Tweet(**payload)

    assert raised.value.errors() == [
        {
            "loc": ("content",),
            "msg": MISSING_FIELD_ERROR_MESSAGE,
            "type": MISSING_FIELD_ERROR_TYPE,
        }
    ]


def test_make_tweet_honours_override():
    """A keyword passed to ``make_tweet`` replaces the payload default."""
    payload = make_tweet(likes_count=OVERRIDDEN_LIKES_COUNT)

    assert payload["likes_count"] == OVERRIDDEN_LIKES_COUNT


def test_make_tweet_override_survives_construction():
    """An overridden value reaches the constructed model."""
    tweet = Tweet(**make_tweet(likes_count=OVERRIDDEN_LIKES_COUNT))

    assert tweet.likes_count == OVERRIDDEN_LIKES_COUNT


def test_make_tweet_timestamp_is_a_datetime():
    """``make_tweet()['timestamp']`` is a ``datetime``, not a string."""
    assert type(make_tweet()["timestamp"]) is datetime

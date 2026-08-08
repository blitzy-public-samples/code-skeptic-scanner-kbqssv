from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schema.tweet import Tweet
from app.schema.user import User
from tests.factories import make_tweet

pytestmark = pytest.mark.unit


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

TWEET_OPTIONAL_FIELD_NAME = "quoted_tweet_id"

TWEET_FIELD_NAMES = TWEET_REQUIRED_FIELD_NAMES + (TWEET_OPTIONAL_FIELD_NAME,)

TWEET_COUNT_FIELD_NAMES = ("likes_count", "retweets_count")

USER_FIELD_NAMES = (
    "user_id",
    "username",
    "display_name",
    "followers_count",
    "created_at",
)

ABSENT_TWEET_FIELD_NAMES = (
    "id",
    "text",
    "user",
    "author",
    "created_at",
    "retweet_count",
    "favorite_count",
)

MISSING_FIELD_ERROR_TYPE = "value_error.missing"

MISSING_FIELD_ERROR_MESSAGE = "field required"

USER_CREATED_AT = datetime(2024, 1, 1, 0, 0, 0)

EXPLICIT_TIMESTAMP = datetime(2023, 6, 15, 12, 30, 45)

COERCED_COUNT = 17

OVERRIDDEN_LIKES_COUNT = 7


def _missing_field_names(error):
    return {
        entry["loc"][0]
        for entry in error.errors()
        if entry["type"] == MISSING_FIELD_ERROR_TYPE
    }


@pytest.fixture
def mock_user_payload():
    return {
        "user_id": "test_user",
        "username": "test_user",
        "display_name": "Test User",
        "followers_count": 3200,
        "created_at": USER_CREATED_AT,
    }


def test_tweet_declares_the_ten_documented_fields():
    assert set(Tweet.__fields__) == set(TWEET_FIELD_NAMES)


def test_tweet_declares_its_fields_in_source_order():
    assert tuple(Tweet.__fields__) == TWEET_FIELD_NAMES


@pytest.mark.parametrize("field_name", TWEET_REQUIRED_FIELD_NAMES)
def test_tweet_field_is_required(field_name):
    assert Tweet.__fields__[field_name].required is True


def test_tweet_requires_exactly_nine_fields():
    required = {
        name for name, field in Tweet.__fields__.items() if field.required
    }

    assert required == set(TWEET_REQUIRED_FIELD_NAMES)


def test_tweet_quoted_tweet_id_is_not_required():
    assert Tweet.__fields__[TWEET_OPTIONAL_FIELD_NAME].required is False


def test_tweet_quoted_tweet_id_defaults_to_none_when_omitted():
    payload = make_tweet()
    payload.pop(TWEET_OPTIONAL_FIELD_NAME)

    assert Tweet(**payload).quoted_tweet_id is None


@pytest.mark.parametrize("field_name", TWEET_COUNT_FIELD_NAMES)
def test_tweet_count_field_coerces_string_to_int(field_name):
    tweet = Tweet(**make_tweet(**{field_name: str(COERCED_COUNT)}))
    value = getattr(tweet, field_name)

    assert value == COERCED_COUNT
    assert type(value) is int


@pytest.mark.parametrize("field_name", TWEET_COUNT_FIELD_NAMES)
def test_tweet_count_field_preserves_int(field_name):
    tweet = Tweet(**make_tweet(**{field_name: COERCED_COUNT}))
    value = getattr(tweet, field_name)

    assert value == COERCED_COUNT
    assert type(value) is int


def test_tweet_doubt_rating_coerces_int_to_float():
    tweet = Tweet(**make_tweet(doubt_rating=1))

    assert tweet.doubt_rating == 1.0
    assert type(tweet.doubt_rating) is float


def test_tweet_timestamp_accepts_datetime():
    tweet = Tweet(**make_tweet(timestamp=EXPLICIT_TIMESTAMP))

    assert tweet.timestamp == EXPLICIT_TIMESTAMP
    assert type(tweet.timestamp) is datetime


def test_tweet_omits_the_names_production_assumes():
    assert set(ABSENT_TWEET_FIELD_NAMES).isdisjoint(Tweet.__fields__)


def test_tweet_ignores_unknown_keyword_arguments():
    unknown = {name: "ignored" for name in ABSENT_TWEET_FIELD_NAMES}

    tweet = Tweet(**make_tweet(), **unknown)
    accepted = {name for name in unknown if hasattr(tweet, name)}

    assert accepted == set()
    assert set(tweet.dict()) == set(TWEET_FIELD_NAMES)


def test_user_declares_the_five_documented_fields():
    assert set(User.__fields__) == set(USER_FIELD_NAMES)


def test_user_declares_its_fields_in_source_order():
    assert tuple(User.__fields__) == USER_FIELD_NAMES


def test_user_requires_every_declared_field():
    required = {
        name for name, field in User.__fields__.items() if field.required
    }

    assert required == set(USER_FIELD_NAMES)


def test_user_accepts_a_complete_payload(mock_user_payload):
    user = User(**mock_user_payload)

    assert {
        name: getattr(user, name) for name in USER_FIELD_NAMES
    } == mock_user_payload


@pytest.mark.parametrize("field_name", USER_FIELD_NAMES)
def test_user_rejects_payload_missing_field(field_name, mock_user_payload):
    mock_user_payload.pop(field_name)

    with pytest.raises(ValidationError) as raised:
        User(**mock_user_payload)

    assert _missing_field_names(raised.value) == {field_name}


def test_make_tweet_supplies_exactly_the_schema_keys():
    assert set(make_tweet()) == set(Tweet.__fields__)


def test_make_tweet_payload_constructs_a_tweet():
    assert isinstance(Tweet(**make_tweet()), Tweet)


@pytest.mark.parametrize("field_name", TWEET_FIELD_NAMES)
def test_make_tweet_value_survives_construction(field_name):
    payload = make_tweet()

    assert getattr(Tweet(**payload), field_name) == payload[field_name]


@pytest.mark.parametrize("field_name", TWEET_FIELD_NAMES)
def test_make_tweet_value_type_survives_construction(field_name):
    payload = make_tweet()
    value = getattr(Tweet(**payload), field_name)

    assert type(value) is type(payload[field_name])


@pytest.mark.parametrize("field_name", TWEET_REQUIRED_FIELD_NAMES)
def test_tweet_rejects_payload_missing_required_field(field_name):
    payload = make_tweet()
    payload.pop(field_name)

    with pytest.raises(ValidationError) as raised:
        Tweet(**payload)

    assert _missing_field_names(raised.value) == {field_name}


def test_tweet_missing_field_error_reports_loc_type_and_message():
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
    payload = make_tweet(likes_count=OVERRIDDEN_LIKES_COUNT)

    assert payload["likes_count"] == OVERRIDDEN_LIKES_COUNT


def test_make_tweet_override_survives_construction():
    tweet = Tweet(**make_tweet(likes_count=OVERRIDDEN_LIKES_COUNT))

    assert tweet.likes_count == OVERRIDDEN_LIKES_COUNT


def test_make_tweet_timestamp_is_a_datetime():
    assert type(make_tweet()["timestamp"]) is datetime

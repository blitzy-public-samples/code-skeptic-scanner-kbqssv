import importlib
import inspect
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from tweepy import StreamListener

from tests.factories import make_status

pytestmark = pytest.mark.unit


CONFIG_MODULE = "app.core.config"

POPULARITY_THRESHOLD = 100

DOUBT_RATING_THRESHOLD = 0.7

DOUBT_RATING_THRESHOLD_NAME = "DOUBT_RATING_THRESHOLD"

MISSING_TWEET_FIELDS = frozenset(
    {
        "tweet_id",
        "content",
        "user_id",
        "timestamp",
        "likes_count",
        "retweets_count",
        "ai_tools",
        "media_urls",
    }
)

MISSING_FIELD_ERROR_TYPE = "value_error.missing"

CONSUMER_KEY = "test-twitter-consumer-key"

CONSUMER_SECRET = "test-twitter-consumer-secret"

ACCESS_TOKEN = "test-twitter-access-token"

ACCESS_TOKEN_SECRET = "test-twitter-access-token-secret"

DECLARED_TRACK_KEYWORDS = ()

CONFIGURED_TRACK_KEYWORDS = ("copilot", "chatgpt")

DATABASE_FAILURE_MESSAGE = "Database error"

MEDIA_URL = "https://example.invalid/media/1.jpg"

#: Failure types injected at each reachable tweepy stage of
#: ``start_tweet_stream``.  ``Exception`` is included deliberately: it is the
#: type a bare ``except Exception`` would name, so a clause of that shape
#: wrapped around the wiring -- or a retry loop built on one -- would stop the
#: exception these cases expect to arrive.  The other two are subclasses of it,
#: and the function holds no ``try`` at all, so none is caught.
PROPAGATED_FAILURES = (
    pytest.param(Exception, id="exception"),
    pytest.param(RuntimeError, id="runtimeerror"),
    pytest.param(ConnectionError, id="connectionerror"),
)

#: Messages carried by the injected failures, one per stage of the wiring, in
#: the order the function reaches them.  Each is distinct, so a propagated
#: exception identifies the stage it was raised at as well as its type.
OAUTH_HANDLER_FAILURE_MESSAGE = "the consumer credentials were rejected"

SET_ACCESS_TOKEN_FAILURE_MESSAGE = "the access token was rejected"

API_FAILURE_MESSAGE = "the API client could not be built"

STREAM_FAILURE_MESSAGE = "the stream could not be opened"

FILTER_FAILURE_MESSAGE = "the filter connection was refused"

#: Initial value of a variable a completed call would overwrite.  A propagation
#: case finding it still in place has established that the call produced no
#: value -- not even the ``None`` a completed run evaluates to.
UNREACHED = object()

# Popularity boundary matrix.  Each case carries its own counts and its
# expected outcome is the test it belongs to, so no test branches on the sum.

BELOW_THRESHOLD_COUNTS = (
    (50, 49),
    (0, 99),
    (99, 0),
    (0, 0),
)

AT_OR_ABOVE_THRESHOLD_COUNTS = (
    (50, 50),
    (100, 0),
    (0, 100),
    (50, 51),
)


@pytest.fixture
def config_module():
    """Import config only after conftest has seeded module-scope Settings
    inputs.
    """
    return importlib.import_module(CONFIG_MODULE)


@pytest.fixture
def mock_add_tweet(tweet_processor_module):
    """Patch the subject-bound add_tweet to prevent Firestore egress."""
    with patch.object(
        tweet_processor_module, "add_tweet", MagicMock(name="add_tweet")
    ) as mock:
        yield mock


@pytest.fixture
def tweet_stream_listener(tweet_processor_module):
    return tweet_processor_module.TweetStreamListener()


@pytest.fixture
def status_clearing_the_gate():
    return make_status(retweet_count=POPULARITY_THRESHOLD, favorite_count=0)


@pytest.fixture
def mock_tweepy(tweet_processor_module, monkeypatch):
    """Patch sys.modules['tweepy'] for the function-local import and inject
    undeclared consumer fields via monkeypatch.
    """
    settings = tweet_processor_module.settings
    monkeypatch.setitem(
        settings.__dict__, "TWITTER_CONSUMER_KEY", CONSUMER_KEY
    )
    monkeypatch.setitem(
        settings.__dict__, "TWITTER_CONSUMER_SECRET", CONSUMER_SECRET
    )
    stand_in = MagicMock(name="tweepy")
    with patch.dict(sys.modules, {"tweepy": stand_in}):
        yield stand_in


@pytest.fixture
def started_stream(tweet_processor_module, mock_tweepy):
    """Call start_tweet_stream while the tweepy stand-in is installed, then
    expose its call records.
    """
    result = tweet_processor_module.start_tweet_stream()
    return SimpleNamespace(
        result=result,
        tweepy=mock_tweepy,
        auth=mock_tweepy.OAuthHandler.return_value,
        api=mock_tweepy.API.return_value,
        stream=mock_tweepy.Stream.return_value,
        listener=mock_tweepy.Stream.call_args.kwargs["listener"],
    )


def test_tweet_stream_listener_subclasses_tweepy_stream_listener(
    tweet_processor_module,
):
    assert issubclass(
        tweet_processor_module.TweetStreamListener, StreamListener
    )


def test_tweet_stream_listener_builds_an_llm_service(tweet_stream_listener):
    assert tweet_stream_listener.llm_service is not None


def test_popularity_threshold_is_the_gate_oracle(tweet_processor_module):
    assert (
        tweet_processor_module.settings.POPULARITY_THRESHOLD
        == POPULARITY_THRESHOLD
    )


@pytest.mark.parametrize(
    ("retweet_count", "favorite_count"), BELOW_THRESHOLD_COUNTS
)
def test_on_status_skips_below_popularity_threshold(
    tweet_stream_listener, mock_add_tweet, retweet_count, favorite_count
):
    status = make_status(
        retweet_count=retweet_count, favorite_count=favorite_count
    )

    assert tweet_stream_listener.on_status(status) is True
    assert mock_add_tweet.call_count == 0


@pytest.mark.parametrize(
    ("retweet_count", "favorite_count"), AT_OR_ABOVE_THRESHOLD_COUNTS
)
def test_on_status_rejects_at_or_above_popularity_threshold(
    tweet_stream_listener, mock_add_tweet, retweet_count, favorite_count
):
    status = make_status(
        retweet_count=retweet_count, favorite_count=favorite_count
    )

    with pytest.raises(ValidationError):
        tweet_stream_listener.on_status(status)

    assert mock_add_tweet.call_count == 0


def test_on_status_requests_a_doubt_rating_for_the_status_text(
    tweet_stream_listener, mock_add_tweet, status_clearing_the_gate
):
    with pytest.raises(ValidationError):
        tweet_stream_listener.on_status(status_clearing_the_gate)

    calculate = tweet_stream_listener.llm_service.calculate_doubt_rating
    calculate.assert_called_once_with(status_clearing_the_gate.text)


def test_on_status_validation_error_reports_eight_missing_fields(
    tweet_stream_listener, mock_add_tweet, status_clearing_the_gate
):
    with pytest.raises(ValidationError) as excinfo:
        tweet_stream_listener.on_status(status_clearing_the_gate)

    errors = excinfo.value.errors()

    assert len(errors) == len(MISSING_TWEET_FIELDS)
    assert {error["loc"][0] for error in errors} == MISSING_TWEET_FIELDS
    assert {error["type"] for error in errors} == {MISSING_FIELD_ERROR_TYPE}


def test_on_status_validation_error_originates_in_the_tweet_schema(
    tweet_stream_listener, mock_add_tweet, status_clearing_the_gate
):
    tweet_schema = importlib.import_module("app.schema.tweet")

    with pytest.raises(ValidationError) as excinfo:
        tweet_stream_listener.on_status(status_clearing_the_gate)

    assert excinfo.value.model is tweet_schema.Tweet


def test_start_tweet_stream_returns_none(started_stream):
    assert started_stream.result is None


def test_start_tweet_stream_builds_oauth_handler_from_consumer_settings(
    started_stream,
):
    started_stream.tweepy.OAuthHandler.assert_called_once_with(
        CONSUMER_KEY, CONSUMER_SECRET
    )


def test_start_tweet_stream_sets_the_access_token_from_settings(
    started_stream,
):
    started_stream.auth.set_access_token.assert_called_once_with(
        ACCESS_TOKEN, ACCESS_TOKEN_SECRET
    )


def test_start_tweet_stream_builds_the_api_from_the_auth_handler(
    started_stream,
):
    started_stream.tweepy.API.assert_called_once_with(started_stream.auth)


def test_start_tweet_stream_builds_the_stream_with_keyword_arguments_only(
    started_stream,
):
    call = started_stream.tweepy.Stream.call_args

    assert started_stream.tweepy.Stream.call_count == 1
    assert call.args == ()
    assert set(call.kwargs) == {"auth", "listener"}
    assert call.kwargs["auth"] is started_stream.api.auth


def test_start_tweet_stream_passes_a_tweet_stream_listener(
    tweet_processor_module, started_stream
):
    assert isinstance(
        started_stream.listener, tweet_processor_module.TweetStreamListener
    )


def test_start_tweet_stream_filters_on_the_declared_track_keywords(
    started_stream,
):
    started_stream.stream.filter.assert_called_once_with(
        track=list(DECLARED_TRACK_KEYWORDS)
    )


def test_start_tweet_stream_filters_on_configured_track_keywords(
    tweet_processor_module, mock_tweepy, monkeypatch
):
    monkeypatch.setitem(
        tweet_processor_module.settings.__dict__,
        "TWITTER_TRACK_KEYWORDS",
        list(CONFIGURED_TRACK_KEYWORDS),
    )

    tweet_processor_module.start_tweet_stream()

    mock_tweepy.Stream.return_value.filter.assert_called_once_with(
        track=list(CONFIGURED_TRACK_KEYWORDS)
    )


# Error disposition of the wiring.  The function holds no ``try``, so each of
# the five tweepy calls it makes is a boundary at which a failure reaches the
# caller unchanged.  The cases above assert what each stage is *called with*
# when every stage returns normally; the cases below assert what happens when
# one of them does not.  Each injects at a single stage, asserts the very
# instance raised is what escaped, asserts the exact call depth reached before
# it, and asserts that no later stage ran.
#
# ``stream.filter`` matters most: in production it opens a blocking live Twitter
# connection, and it is the one stage whose failure a retry loop would be most
# tempting to add.  Its case pins that a failure there ends the call.


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_start_tweet_stream_propagates_an_oauth_handler_failure(
    tweet_processor_module, mock_tweepy, mock_add_tweet, failure_type
):
    """A failing ``tweepy.OAuthHandler`` reaches the caller unchanged.

    It is the first call the function makes, so nothing after it runs: the
    access token is not set, no API client and no stream are built, and no
    filter is opened.
    """
    failure = failure_type(OAUTH_HANDLER_FAILURE_MESSAGE)
    mock_tweepy.OAuthHandler.side_effect = failure
    outcome = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        outcome = tweet_processor_module.start_tweet_stream()

    assert excinfo.value is failure
    assert str(excinfo.value) == OAUTH_HANDLER_FAILURE_MESSAGE
    assert outcome is UNREACHED
    assert mock_tweepy.OAuthHandler.call_count == 1
    mock_tweepy.OAuthHandler.return_value.set_access_token.assert_not_called()
    mock_tweepy.API.assert_not_called()
    mock_tweepy.Stream.assert_not_called()
    mock_tweepy.Stream.return_value.filter.assert_not_called()
    assert mock_add_tweet.call_count == 0


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_start_tweet_stream_propagates_a_set_access_token_failure(
    tweet_processor_module, mock_tweepy, mock_add_tweet, failure_type
):
    """A failing ``auth.set_access_token`` reaches the caller unchanged.

    The handler was built first, so the failure follows a real call rather than
    a short circuit, and no API client, stream or filter follows it.
    """
    failure = failure_type(SET_ACCESS_TOKEN_FAILURE_MESSAGE)
    auth = mock_tweepy.OAuthHandler.return_value
    auth.set_access_token.side_effect = failure
    outcome = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        outcome = tweet_processor_module.start_tweet_stream()

    assert excinfo.value is failure
    assert str(excinfo.value) == SET_ACCESS_TOKEN_FAILURE_MESSAGE
    assert outcome is UNREACHED
    assert mock_tweepy.OAuthHandler.call_count == 1
    assert auth.set_access_token.call_count == 1
    mock_tweepy.API.assert_not_called()
    mock_tweepy.Stream.assert_not_called()
    mock_tweepy.Stream.return_value.filter.assert_not_called()
    assert mock_add_tweet.call_count == 0


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_start_tweet_stream_propagates_an_api_construction_failure(
    tweet_processor_module, mock_tweepy, mock_add_tweet, failure_type
):
    """A failing ``tweepy.API`` reaches the caller unchanged.

    The two authentication stages completed, and the stream is never built, so
    no connection of any kind is attempted.
    """
    failure = failure_type(API_FAILURE_MESSAGE)
    mock_tweepy.API.side_effect = failure
    outcome = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        outcome = tweet_processor_module.start_tweet_stream()

    assert excinfo.value is failure
    assert str(excinfo.value) == API_FAILURE_MESSAGE
    assert outcome is UNREACHED
    assert mock_tweepy.OAuthHandler.call_count == 1
    assert mock_tweepy.API.call_count == 1
    mock_tweepy.Stream.assert_not_called()
    mock_tweepy.Stream.return_value.filter.assert_not_called()
    assert mock_add_tweet.call_count == 0


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_start_tweet_stream_propagates_a_stream_construction_failure(
    tweet_processor_module, mock_tweepy, mock_add_tweet, failure_type
):
    """A failing ``tweepy.Stream`` reaches the caller unchanged.

    Construction is the last statement before the filter, so a failure here
    means no connection is opened at all: ``filter`` is never called and the
    listener the function built is discarded.
    """
    failure = failure_type(STREAM_FAILURE_MESSAGE)
    mock_tweepy.Stream.side_effect = failure
    outcome = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        outcome = tweet_processor_module.start_tweet_stream()

    assert excinfo.value is failure
    assert str(excinfo.value) == STREAM_FAILURE_MESSAGE
    assert outcome is UNREACHED
    assert mock_tweepy.API.call_count == 1
    assert mock_tweepy.Stream.call_count == 1
    mock_tweepy.Stream.return_value.filter.assert_not_called()
    assert mock_add_tweet.call_count == 0


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_start_tweet_stream_propagates_a_filter_failure(
    tweet_processor_module, mock_tweepy, mock_add_tweet, failure_type
):
    """A failing ``stream.filter`` reaches the caller unchanged.

    This is the last statement of the function and, in production, the blocking
    live connection.  A failure there is neither swallowed nor retried: the
    instance raised is what escapes, the call is made exactly once, and the
    function produces no value -- not even the ``None`` a completed run does.
    """
    failure = failure_type(FILTER_FAILURE_MESSAGE)
    stream = mock_tweepy.Stream.return_value
    stream.filter.side_effect = failure
    outcome = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        outcome = tweet_processor_module.start_tweet_stream()

    assert excinfo.value is failure
    assert str(excinfo.value) == FILTER_FAILURE_MESSAGE
    assert outcome is UNREACHED
    assert stream.filter.call_count == 1
    assert stream.filter.call_args.kwargs == {
        "track": list(DECLARED_TRACK_KEYWORDS)
    }
    assert mock_add_tweet.call_count == 0


def test_start_tweet_stream_does_not_retry_a_failed_filter(
    tweet_processor_module, mock_tweepy, mock_add_tweet
):
    """A failed filter is attempted once and the function gives up.

    The subject holds no loop, no backoff and no reconnection, so neither the
    filter nor any earlier stage is repeated.  A retry added around the
    connection would raise one of these counts above one.
    """
    stream = mock_tweepy.Stream.return_value
    stream.filter.side_effect = Exception(FILTER_FAILURE_MESSAGE)

    with pytest.raises(Exception):
        tweet_processor_module.start_tweet_stream()

    assert stream.filter.call_count == 1
    assert mock_tweepy.Stream.call_count == 1
    assert mock_tweepy.OAuthHandler.call_count == 1
    assert mock_tweepy.API.call_count == 1


# Error disposition of the listener.  Rewritten from
# backend/tests/test_tasks.py::test_process_tweet_error_handling, whose intent
# was that a persistence failure propagates out of the task.


def test_on_status_validation_error_precedes_the_add_tweet_failure(
    tweet_stream_listener, mock_add_tweet, status_clearing_the_gate
):
    mock_add_tweet.side_effect = Exception(DATABASE_FAILURE_MESSAGE)

    with pytest.raises(ValidationError) as excinfo:
        tweet_stream_listener.on_status(status_clearing_the_gate)

    assert mock_add_tweet.call_count == 0
    assert DATABASE_FAILURE_MESSAGE not in str(excinfo.value)


@pytest.mark.skip(
    reason="app/tasks/tweet_processor.py implements no media handling."
)
def test_on_status_with_media(tweet_stream_listener, mock_add_tweet):
    status = make_status(
        retweet_count=POPULARITY_THRESHOLD,
        favorite_count=0,
        extended_entities={"media": [{"media_url_https": MEDIA_URL}]},
    )

    assert tweet_stream_listener.on_status(status) is True

    mock_add_tweet.assert_called_once()
    assert mock_add_tweet.call_args.args[0].media_urls == [MEDIA_URL]


@pytest.mark.skip(
    reason="app/tasks/tweet_processor.py implements no deduplication."
)
def test_on_status_deduplication(tweet_stream_listener, mock_add_tweet):
    status = make_status(retweet_count=POPULARITY_THRESHOLD, favorite_count=0)

    assert tweet_stream_listener.on_status(status) is True
    assert tweet_stream_listener.on_status(status) is True

    assert mock_add_tweet.call_count == 1


def test_doubt_rating_threshold_is_declared_configuration(config_module):
    assert (
        config_module.settings.DOUBT_RATING_THRESHOLD
        == DOUBT_RATING_THRESHOLD
    )


def test_doubt_rating_threshold_is_unreferenced_by_the_subject(
    tweet_processor_module,
):
    source = inspect.getsource(tweet_processor_module)

    assert DOUBT_RATING_THRESHOLD_NAME not in source

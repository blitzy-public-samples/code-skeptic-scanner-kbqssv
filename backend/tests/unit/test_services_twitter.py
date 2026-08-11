"""Unit suite for ``app/services/twitter_service.py``.

Covers the module's whole public surface -- ``TwitterStreamListener`` and
``start_twitter_stream`` -- together with the module-scope ``settings``
instance the stream starter reads.

Current behaviour captured as divergence
----------------------------------------
Neither of the subject's two entry points can complete.  Both terminal states
are what this suite asserts.

``TwitterStreamListener.on_status`` builds its payload from four keys --
``id``, ``text``, ``user`` and ``created_at`` -- and ``app/schema/tweet.py``
declares none of them.  Constructing ``Tweet`` therefore raises a pydantic
``ValidationError`` naming every one of the schema's nine required fields, so
the listener can never persist a tweet: ``add_tweet`` is unreachable, and so
is the trailing ``return True``.  pydantic v1 ignores keyword arguments that
name no field, so the four keys the listener does supply contribute no error
of their own and the count is exactly the nine that are missing.
:data:`MISSING_TWEET_FIELDS` is that set.

``start_twitter_stream`` is dead code.  It reads
``settings.TWITTER_CONSUMER_KEY`` and ``settings.TWITTER_CONSUMER_SECRET``,
which ``Settings`` does not declare -- the declared names are
``TWITTER_API_KEY`` and ``TWITTER_API_SECRET`` -- so in its natural state the
first statement raises ``AttributeError``.  Supplied with those two values it
proceeds exactly three statements further, then reaches a ``tweepy.Stream``
reference.  The subject imports ``StreamListener``, ``OAuthHandler`` and
``API`` *from* tweepy and never imports the module name, so that reference
raises ``NameError`` unconditionally and the ``stream.filter`` call after it
can never execute.

The class the legacy suite expected does not exist.  The removed
``backend/tests/test_services.py`` imported a ``TwitterService`` class and
called ``process_tweets`` on it; the subject exposes free functions and a
listener class only.  :data:`LEGACY_PHANTOM_NAMES` pins the absence of the
three method names that suite asserted against.

Error disposition
-----------------
The subject holds no ``try`` anywhere, so each of the three tweepy calls that
do execute is a boundary at which a failure reaches the caller unchanged.  The
wiring cases assert what each stage is called with when it returns normally;
the disposition cases assert that a failure raised by any of them escapes as
the very instance raised, that it is not converted into the ``NameError`` the
function otherwise terminates with, and that no later stage runs and no stage
is retried.

Assertion form
--------------
Every expectation here is an exception type plus a substring of its message,
an exception identity, or a call-argument oracle.  No assertion names a line
number of the subject.

Safety
------
``start_twitter_stream`` ends in ``stream.filter(...)``, a blocking live
Twitter connection.  No test in this module lets execution reach it, and three
independent barriers hold that true:

* the natural state raises before the first assignment completes, and the
  supplied state raises at the ``tweepy`` reference;
* :func:`mock_twitter_client` replaces ``OAuthHandler`` and ``API`` on the
  subject, so no Twitter client is constructed even for the statements that do
  run, and :func:`mock_add_tweet` replaces the Firestore writer the subject
  bound, so no test can reach Google Cloud;
* the stand-in :func:`mock_stream_settings` installs carries no
  ``TWITTER_TRACK_KEYWORDS``, so evaluating the argument of ``stream.filter``
  raises ``AttributeError`` on the stand-in — execution stops one statement
  short of the connection even without the ``NameError`` above it.

Shared infrastructure
---------------------
``backend/tests/conftest.py`` is the sole installer of the autouse credential
neutraliser and the egress guard, and this module installs neither.  The
guard is the backstop behind the patches above.  Status objects come from
``backend/tests/factories.py``; no payload is built inline.

Isolation
---------
``app/services/twitter_service.py`` builds its own ``Settings`` at module
scope, so it is not the ``app.core.config`` singleton, and every test that
supplies the two undeclared consumer fields does so by replacing that module
attribute with a stand-in for the duration of one test.  The natural-state
tests are declared after the supplied-state tests, and each assertion holds
under either order because no stand-in outlives its test.

.. seealso::

   ``docs/testing/DECISION-LOG.md`` rows D151 (the layered stream safety and the
   keyword-less stand-in), D150 (supplying fields ``Settings`` never declares),
   D149 (the patch boundary), D105 (the egress guard behind it), D106 (the
   ``TwitterService`` shim whose absence is pinned here) and D53 (production
   defects are pinned, not repaired).
   ``docs/testing/TRACEABILITY-MATRIX.md`` records the legacy constructs this
   suite replaces.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from tweepy import StreamListener

import app.core.config as config
import app.services.twitter_service as twitter_service
from tests.factories import make_status

pytestmark = pytest.mark.unit


MISSING_TWEET_FIELDS = frozenset(
    {
        "tweet_id",
        "content",
        "user_id",
        "timestamp",
        "likes_count",
        "retweets_count",
        "doubt_rating",
        "ai_tools",
        "media_urls",
    }
)

MISSING_TWEET_FIELD_COUNT = 9

MISSING_FIELD_ERROR_TYPE = "value_error.missing"

MISSING_FIELD_ERROR_MESSAGE = "field required"

DEFAULTED_TWEET_FIELD = "quoted_tweet_id"

UNDECLARED_CONSUMER_KEY_FIELD = "TWITTER_CONSUMER_KEY"

UNDECLARED_CONSUMER_SECRET_FIELD = "TWITTER_CONSUMER_SECRET"

UNDECLARED_CONSUMER_FIELDS = (
    UNDECLARED_CONSUMER_KEY_FIELD,
    UNDECLARED_CONSUMER_SECRET_FIELD,
)

UNIMPORTED_MODULE_ERROR = "name 'tweepy' is not defined"

UNIMPORTED_MODULE_NAME = "tweepy"

ABSENT_AUTHOR_ERROR = "'NoneType' object has no attribute 'screen_name'"

LEGACY_SERVICE_CLASS = "TwitterService"

LEGACY_PHANTOM_NAMES = (
    "process_tweets",
    "process_sentiment",
    "calculate_engagement_rate",
)

PUBLIC_MODULE_NAMES = frozenset(
    {
        "API",
        "OAuthHandler",
        "Settings",
        "StreamListener",
        "Tweet",
        "TwitterStreamListener",
        "add_tweet",
        "settings",
        "start_twitter_stream",
    }
)


STAND_IN_CONSUMER_KEY = "blitzy-test-consumer-key-not-a-real-credential"

STAND_IN_CONSUMER_SECRET = "blitzy-test-consumer-secret-not-a-real-credential"

STAND_IN_ACCESS_TOKEN = "blitzy-test-access-token-not-a-real-credential"

STAND_IN_ACCESS_TOKEN_SECRET = (
    "blitzy-test-access-token-secret-not-a-real-credential"
)

UNREACHED = object()

#: Failure types injected at the three reachable tweepy stages.  ``Exception``
#: is included: it is the type a bare ``except Exception`` would
#: name, so a clause of that shape wrapped around the stream starter would stop
#: the exception these cases expect to arrive.  The other two are subclasses of
#: it and none of them is caught either -- the subject holds no ``try`` at all.
PROPAGATED_FAILURES = (
    pytest.param(Exception, id="exception"),
    pytest.param(RuntimeError, id="runtimeerror"),
    pytest.param(ConnectionError, id="connectionerror"),
)

#: Messages carried by the injected failures, one per reachable stage.  Each is
#: distinct, so a propagated exception identifies the stage it was raised at as
#: well as its type, and none of them is the ``NameError`` message the function
#: ends with when every stage returns normally.
OAUTH_HANDLER_FAILURE_MESSAGE = "the consumer credentials were rejected"

SET_ACCESS_TOKEN_FAILURE_MESSAGE = "the access token was rejected"

API_FAILURE_MESSAGE = "the API client could not be built"


@pytest.fixture
def mock_add_tweet():
    """Patch the subject-bound add_tweet to prevent Firestore egress."""
    with patch.object(twitter_service, "add_tweet") as writer:
        yield writer


@pytest.fixture
def mock_status():
    return make_status()


@pytest.fixture
def mock_listener():
    return twitter_service.TwitterStreamListener()


@pytest.fixture
def mock_stream_settings(monkeypatch):
    """Replace subject-local settings with a stand-in for undeclared consumer
    fields; monkeypatch restores it.
    """
    stand_in = SimpleNamespace(
        TWITTER_CONSUMER_KEY=STAND_IN_CONSUMER_KEY,
        TWITTER_CONSUMER_SECRET=STAND_IN_CONSUMER_SECRET,
        TWITTER_ACCESS_TOKEN=STAND_IN_ACCESS_TOKEN,
        TWITTER_ACCESS_TOKEN_SECRET=STAND_IN_ACCESS_TOKEN_SECRET,
    )
    monkeypatch.setattr(twitter_service, "settings", stand_in)
    return stand_in


@pytest.fixture
def mock_twitter_client():
    """Patch the OAuthHandler and API names bound by the subject."""
    oauth_handler = MagicMock(name="OAuthHandler")
    api = MagicMock(name="API")
    with patch.object(
        twitter_service, "OAuthHandler", oauth_handler
    ), patch.object(twitter_service, "API", api):
        yield SimpleNamespace(
            oauth_handler=oauth_handler,
            api=api,
            auth=oauth_handler.return_value,
        )


def test_module_does_not_expose_twitter_service_class():
    assert not hasattr(twitter_service, LEGACY_SERVICE_CLASS)


@pytest.mark.parametrize("method_name", LEGACY_PHANTOM_NAMES)
def test_module_does_not_expose_legacy_service_method(method_name):
    assert not hasattr(twitter_service, method_name)


def test_module_public_surface_is_exactly_nine_names():
    exposed = {
        name for name in vars(twitter_service) if not name.startswith("_")
    }

    assert exposed == set(PUBLIC_MODULE_NAMES)


def test_twitter_stream_listener_is_a_class():
    assert isinstance(twitter_service.TwitterStreamListener, type)


def test_twitter_stream_listener_subclasses_stream_listener():
    assert issubclass(twitter_service.TwitterStreamListener, StreamListener)


def test_twitter_stream_listener_defines_on_status():
    assert "on_status" in vars(twitter_service.TwitterStreamListener)


def test_start_twitter_stream_is_callable():
    assert callable(twitter_service.start_twitter_stream)


def test_module_does_not_bind_the_tweepy_module_name():
    assert not hasattr(twitter_service, UNIMPORTED_MODULE_NAME)


def test_module_settings_is_an_independent_instance():
    assert isinstance(twitter_service.settings, config.Settings)
    assert twitter_service.settings is not config.settings


@pytest.mark.parametrize("field_name", UNDECLARED_CONSUMER_FIELDS)
def test_settings_does_not_declare_consumer_field(field_name):
    assert field_name not in config.Settings.__fields__
    assert not hasattr(twitter_service.settings, field_name)


def test_on_status_raises_validation_error(
    mock_listener, mock_status, mock_add_tweet
):
    with pytest.raises(ValidationError):
        mock_listener.on_status(mock_status)


def test_on_status_does_not_return_true(
    mock_listener, mock_status, mock_add_tweet
):
    outcome = UNREACHED

    with pytest.raises(ValidationError):
        outcome = mock_listener.on_status(mock_status)

    assert outcome is UNREACHED


def test_on_status_reports_nine_missing_fields(
    mock_listener, mock_status, mock_add_tweet
):
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    assert len(excinfo.value.errors()) == MISSING_TWEET_FIELD_COUNT


def test_on_status_names_every_required_schema_field(
    mock_listener, mock_status, mock_add_tweet
):
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    reported = {error["loc"][0] for error in excinfo.value.errors()}

    assert reported == set(MISSING_TWEET_FIELDS)


def test_on_status_omits_the_defaulted_schema_field(
    mock_listener, mock_status, mock_add_tweet
):
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    reported = {error["loc"][0] for error in excinfo.value.errors()}

    assert DEFAULTED_TWEET_FIELD not in reported


def test_on_status_reports_only_missing_field_errors(
    mock_listener, mock_status, mock_add_tweet
):
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    errors = excinfo.value.errors()

    assert {error["type"] for error in errors} == {MISSING_FIELD_ERROR_TYPE}
    assert {error["msg"] for error in errors} == {MISSING_FIELD_ERROR_MESSAGE}
    assert {len(error["loc"]) for error in errors} == {1}


def test_on_status_validation_error_names_the_tweet_model(
    mock_listener, mock_status, mock_add_tweet
):
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    assert excinfo.value.model is twitter_service.Tweet


def test_on_status_does_not_persist_the_tweet(
    mock_listener, mock_status, mock_add_tweet
):
    with pytest.raises(ValidationError):
        mock_listener.on_status(mock_status)

    assert mock_add_tweet.call_count == 0


def test_on_status_absent_author_raises_attribute_error(
    mock_listener, mock_add_tweet
):
    with pytest.raises(AttributeError, match=ABSENT_AUTHOR_ERROR):
        mock_listener.on_status(make_status(user=None))

    assert mock_add_tweet.call_count == 0


def test_start_twitter_stream_raises_name_error(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()


def test_start_twitter_stream_does_not_return(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    outcome = UNREACHED

    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        outcome = twitter_service.start_twitter_stream()

    assert outcome is UNREACHED


def test_start_twitter_stream_builds_the_oauth_handler(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()

    assert mock_twitter_client.oauth_handler.call_count == 1
    assert mock_twitter_client.oauth_handler.call_args[0] == (
        STAND_IN_CONSUMER_KEY,
        STAND_IN_CONSUMER_SECRET,
    )
    assert mock_twitter_client.oauth_handler.call_args[1] == {}


def test_start_twitter_stream_sets_the_access_token(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()

    set_access_token = mock_twitter_client.auth.set_access_token

    assert set_access_token.call_count == 1
    assert set_access_token.call_args[0] == (
        STAND_IN_ACCESS_TOKEN,
        STAND_IN_ACCESS_TOKEN_SECRET,
    )
    assert set_access_token.call_args[1] == {}


def test_start_twitter_stream_builds_the_api_client(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()

    assert mock_twitter_client.api.call_count == 1
    assert mock_twitter_client.api.call_args[0] == (mock_twitter_client.auth,)
    assert mock_twitter_client.api.call_args[1] == {}


def test_start_twitter_stream_does_not_read_track_keywords(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()

    assert not hasattr(mock_stream_settings, "TWITTER_TRACK_KEYWORDS")


def test_start_twitter_stream_does_not_persist_a_tweet(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()

    assert mock_add_tweet.call_count == 0


# Error disposition of the three reachable tweepy stages.
#
# The subject holds no ``try``, so each of the three calls that do execute --
# ``OAuthHandler``, ``auth.set_access_token`` and ``API`` -- is a boundary at
# which a failure reaches the caller unchanged.  The cases above assert what
# each stage is *called with* when it returns normally; the cases below assert
# what happens when it does not.  Each injects at one stage and asserts that the
# very instance raised is what escaped, that the ``NameError`` the function
# otherwise ends with never arrives, and that no later stage ran.


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_start_twitter_stream_propagates_an_oauth_handler_failure(
    mock_stream_settings, mock_twitter_client, mock_add_tweet, failure_type
):
    """A failing ``OAuthHandler`` reaches the caller from the first statement.

    Nothing after it runs: the access token is not set, no API client is built,
    and the function produces no value.
    """
    failure = failure_type(OAUTH_HANDLER_FAILURE_MESSAGE)
    mock_twitter_client.oauth_handler.side_effect = failure
    outcome = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        outcome = twitter_service.start_twitter_stream()

    assert excinfo.value is failure
    assert str(excinfo.value) == OAUTH_HANDLER_FAILURE_MESSAGE
    assert outcome is UNREACHED
    assert mock_twitter_client.oauth_handler.call_count == 1
    mock_twitter_client.auth.set_access_token.assert_not_called()
    mock_twitter_client.api.assert_not_called()
    assert mock_add_tweet.call_count == 0


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_start_twitter_stream_propagates_a_set_access_token_failure(
    mock_stream_settings, mock_twitter_client, mock_add_tweet, failure_type
):
    """A failing ``set_access_token`` reaches the caller unchanged.

    The handler was built and the token was attempted, so the failure follows a
    real call rather than a short circuit, and the API client is never built.
    """
    failure = failure_type(SET_ACCESS_TOKEN_FAILURE_MESSAGE)
    mock_twitter_client.auth.set_access_token.side_effect = failure
    outcome = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        outcome = twitter_service.start_twitter_stream()

    assert excinfo.value is failure
    assert str(excinfo.value) == SET_ACCESS_TOKEN_FAILURE_MESSAGE
    assert outcome is UNREACHED
    assert mock_twitter_client.oauth_handler.call_count == 1
    assert mock_twitter_client.auth.set_access_token.call_count == 1
    mock_twitter_client.api.assert_not_called()
    assert mock_add_tweet.call_count == 0


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_start_twitter_stream_propagates_an_api_construction_failure(
    mock_stream_settings, mock_twitter_client, mock_add_tweet, failure_type
):
    """A failing ``API`` reaches the caller instead of the ``NameError``.

    ``API`` is the last statement that executes before the unbound ``tweepy``
    reference, so this is the case that establishes the function does not
    convert an earlier failure into that terminal ``NameError``: the injected
    instance is what escapes, and its message is not the ``NameError``'s.
    """
    failure = failure_type(API_FAILURE_MESSAGE)
    mock_twitter_client.api.side_effect = failure
    outcome = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        outcome = twitter_service.start_twitter_stream()

    assert excinfo.value is failure
    assert str(excinfo.value) == API_FAILURE_MESSAGE
    assert UNIMPORTED_MODULE_ERROR not in str(excinfo.value)
    assert outcome is UNREACHED
    assert mock_twitter_client.api.call_count == 1
    assert mock_add_tweet.call_count == 0


def test_start_twitter_stream_does_not_retry_a_failed_stage(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    """A failed stage is attempted once and the function gives up.

    The subject holds no loop and no retry, so the failing call is made exactly
    once and no later stage compensates for it.  A retry added around the
    handler would raise this call count above one.
    """
    mock_twitter_client.oauth_handler.side_effect = Exception(
        OAUTH_HANDLER_FAILURE_MESSAGE
    )

    with pytest.raises(Exception):
        twitter_service.start_twitter_stream()

    assert mock_twitter_client.oauth_handler.call_count == 1
    assert mock_twitter_client.api.call_count == 0


# ``start_twitter_stream`` in its natural state.  Ordered after the tests
# above, so a forward run reads the subject's real ``Settings`` back.


def test_start_twitter_stream_without_consumer_fields_raises_attribute_error(
    mock_add_tweet,
):
    with pytest.raises(AttributeError, match=UNDECLARED_CONSUMER_KEY_FIELD):
        twitter_service.start_twitter_stream()


def test_start_twitter_stream_natural_state_does_not_return(mock_add_tweet):
    outcome = UNREACHED

    with pytest.raises(AttributeError, match=UNDECLARED_CONSUMER_KEY_FIELD):
        outcome = twitter_service.start_twitter_stream()

    assert outcome is UNREACHED


def test_start_twitter_stream_natural_state_does_not_persist_a_tweet(
    mock_add_tweet,
):
    with pytest.raises(AttributeError, match=UNDECLARED_CONSUMER_KEY_FIELD):
        twitter_service.start_twitter_stream()

    assert mock_add_tweet.call_count == 0

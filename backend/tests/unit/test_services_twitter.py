"""Unit suite for ``app/services/twitter_service.py``.

Covers the module's whole public surface -- ``TwitterStreamListener`` and
``start_twitter_stream`` -- together with the module-scope ``settings``
instance the stream starter reads.

Current behaviour captured as divergence
----------------------------------------
Neither of the subject's two entry points can complete, and this suite
asserts both terminal states rather than the behaviour the design documents
describe.

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
three method names that suite asserted against, so their removal stays
visible.

Assertion form
--------------
Every expectation here is an exception type plus a substring of its message,
or a call-argument oracle.  No assertion names a line number of the subject.

Safety
------
``start_twitter_stream`` ends in ``stream.filter(...)``, a blocking live
Twitter connection.  No test in this module lets execution reach it: the
natural state raises before the first assignment completes, and the supplied
state raises at the ``tweepy`` reference.  :func:`mock_twitter_client`
additionally replaces ``OAuthHandler`` and ``API`` on the subject so no
Twitter client is constructed even for the statements that do run, and
:func:`mock_add_tweet` replaces the Firestore writer the subject bound, so no
test can reach Google Cloud.  The stand-in :func:`mock_stream_settings`
installs carries no ``TWITTER_TRACK_KEYWORDS``: evaluating the argument of
``stream.filter`` raises ``AttributeError`` on the stand-in, so execution
stops one statement short of the connection even if the ``NameError`` above
it ever stops arriving.

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
tests are ordered after the supplied-state tests, so a forward run asserts
the ``AttributeError`` against a subject whose real ``Settings`` has already
been restored.
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

# Oracles.  Every value below was obtained by executing the subject under
# the pinned CPython 3.9 / pydantic 1.10 / tweepy 3.10 stack.

#: The nine fields ``app/schema/tweet.py`` declares without a default, which
#: are exactly the fields ``on_status`` omits.  ``quoted_tweet_id`` is
#: ``Optional[str] = None`` and is absent from this set: a defaulted field
#: contributes no error.  The payload ``app/tasks/tweet_processor.py`` builds
#: supplies ``doubt_rating``, so the suite covering that module reports one
#: fewer.
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

#: Number of errors ``Tweet(**tweet_data)`` reports from ``on_status``.  The
#: cardinality of :data:`MISSING_TWEET_FIELDS`, stated independently so a
#: change to either has to be reconciled against the other.
MISSING_TWEET_FIELD_COUNT = 9

#: ``type`` pydantic v1 gives an error raised by an absent required field.
MISSING_FIELD_ERROR_TYPE = "value_error.missing"

#: ``msg`` pydantic v1 gives an error raised by an absent required field.
MISSING_FIELD_ERROR_MESSAGE = "field required"

#: Field the schema declares with a default.  Absent from every error the
#: listener produces, which is what distinguishes "nine required fields are
#: missing" from "the payload is unrecognised".
DEFAULTED_TWEET_FIELD = "quoted_tweet_id"

#: First ``Settings`` attribute ``start_twitter_stream`` reads, and the
#: substring the natural-state assertions match on.  The whole message reads
#: ``'Settings' object has no attribute 'TWITTER_CONSUMER_KEY'``.
UNDECLARED_CONSUMER_KEY_FIELD = "TWITTER_CONSUMER_KEY"

UNDECLARED_CONSUMER_SECRET_FIELD = "TWITTER_CONSUMER_SECRET"

#: Both names the subject reads off ``settings`` although ``Settings``
#: declares neither.
UNDECLARED_CONSUMER_FIELDS = (
    UNDECLARED_CONSUMER_KEY_FIELD,
    UNDECLARED_CONSUMER_SECRET_FIELD,
)

#: Message of the ``NameError`` that terminates ``start_twitter_stream``.
#: Used as a ``pytest.raises`` pattern; it carries no regular-expression
#: metacharacter.
UNIMPORTED_MODULE_ERROR = "name 'tweepy' is not defined"

#: Name the subject never binds, which is what makes
#: :data:`UNIMPORTED_MODULE_ERROR` unconditional.
UNIMPORTED_MODULE_NAME = "tweepy"

#: Message raised when a status carries no author object.  ``on_status``
#: reads ``status.user.screen_name`` while assembling the payload, before any
#: validation happens.
ABSENT_AUTHOR_ERROR = "'NoneType' object has no attribute 'screen_name'"

#: Class the legacy suite constructed and the subject does not define.
LEGACY_SERVICE_CLASS = "TwitterService"

#: Method names ``backend/tests/test_services.py`` called on the three
#: service classes it expected.  The subject defines none of them.
LEGACY_PHANTOM_NAMES = (
    "process_tweets",
    "process_sentiment",
    "calculate_engagement_rate",
)

#: Every name the subject exposes without a leading underscore, asserted as a
#: whole set.
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

# Credentials supplied to the subject.  Every value is an obvious
# placeholder; this suite reads no credential from the environment and uses
# none that a provider could accept.  All four are mutually distinct, so each
# call-argument assertion identifies the settings field its value came from.

STAND_IN_CONSUMER_KEY = "blitzy-test-consumer-key-not-a-real-credential"

STAND_IN_CONSUMER_SECRET = "blitzy-test-consumer-secret-not-a-real-credential"

STAND_IN_ACCESS_TOKEN = "blitzy-test-access-token-not-a-real-credential"

STAND_IN_ACCESS_TOKEN_SECRET = (
    "blitzy-test-access-token-secret-not-a-real-credential"
)

#: Initial value of a variable that a completed call would overwrite.  A test
#: finding it still in place has established that the call produced no value.
UNREACHED = object()


@pytest.fixture
def mock_add_tweet():
    """Replace the Firestore writer ``app/services/twitter_service.py`` bound.

    The subject imports ``add_tweet`` into its own namespace, so the name
    this fixture replaces is the one ``on_status`` calls; patching
    ``app.db.firestore`` would leave the subject's binding intact.  The real
    function opens a Google Cloud client and writes, so no test in this
    module calls into the subject without it.

    Yields the :class:`unittest.mock.MagicMock` standing in for the writer.
    """
    with patch.object(twitter_service, "add_tweet") as writer:
        yield writer


@pytest.fixture
def mock_status():
    """Return the tweepy status ``on_status`` consumes.

    Built by ``make_status`` from ``backend/tests/factories.py``, which
    exposes ``id_str``, ``text``, ``user.screen_name`` and ``created_at`` --
    the four attributes the listener reads -- plus ``retweet_count`` and
    ``favorite_count``, which this listener ignores.
    """
    return make_status()


@pytest.fixture
def mock_listener():
    """Return a ``TwitterStreamListener``.

    Construction runs the subject's ``__init__``, which delegates to tweepy's
    ``StreamListener.__init__``.  That reaches no network and reads no
    credential, so the real class is instantiated and its base is left in
    place.
    """
    return twitter_service.TwitterStreamListener()


@pytest.fixture
def mock_stream_settings(monkeypatch):
    """Supply the two consumer fields ``Settings`` does not declare.

    Replaces the subject's module-scope ``settings`` with a stand-in exposing
    exactly the four fields the reachable statements of
    ``start_twitter_stream`` read.  The replacement is undone when the test
    ends; the two consumer fields stay undeclared on production ``Settings``,
    and no test writes to a ``Settings`` instance.

    The stand-in carries no ``TWITTER_TRACK_KEYWORDS``, which is read only by
    the unreachable ``stream.filter`` call.

    Yields the :class:`types.SimpleNamespace` stand-in.
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
    """Replace the two tweepy constructors the subject bound.

    The subject imported ``OAuthHandler`` and ``API`` into its own namespace,
    and both are replaced there.  With both replaced, the three statements
    ``start_twitter_stream`` reaches construct no Twitter client.

    Yields a :class:`types.SimpleNamespace` carrying ``oauth_handler``,
    ``api`` and ``auth`` -- the last being the object ``OAuthHandler``
    returns, which is what ``set_access_token`` is called on.
    """
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


# The surface the subject exposes, and the surface the legacy suite expected.


def test_module_does_not_expose_twitter_service_class():
    """The ``TwitterService`` class the legacy suite constructed is absent.

    ``backend/tests/test_services.py`` did ``from services.twitter_service
    import TwitterService`` and built one in ``setUp``.  The subject defines
    a listener class and a free function instead.
    """
    assert not hasattr(twitter_service, LEGACY_SERVICE_CLASS)


@pytest.mark.parametrize("method_name", LEGACY_PHANTOM_NAMES)
def test_module_does_not_expose_legacy_service_method(method_name):
    """No name the legacy suite called as a service method is defined."""
    assert not hasattr(twitter_service, method_name)


def test_module_public_surface_is_exactly_nine_names():
    """The subject exposes only the names :data:`PUBLIC_MODULE_NAMES` lists."""
    exposed = {
        name for name in vars(twitter_service) if not name.startswith("_")
    }

    assert exposed == set(PUBLIC_MODULE_NAMES)


def test_twitter_stream_listener_is_a_class():
    assert isinstance(twitter_service.TwitterStreamListener, type)


def test_twitter_stream_listener_subclasses_stream_listener():
    """The listener extends tweepy's ``StreamListener``.

    The base class was removed in tweepy 4.x, so the subject is importable
    only against the ``tweepy==3.10.0`` pin in
    ``backend/requirements-dev.txt``.
    """
    assert issubclass(twitter_service.TwitterStreamListener, StreamListener)


def test_twitter_stream_listener_defines_on_status():
    """``on_status`` is the subject's own override, not tweepy's."""
    assert "on_status" in vars(twitter_service.TwitterStreamListener)


def test_start_twitter_stream_is_callable():
    assert callable(twitter_service.start_twitter_stream)


def test_module_does_not_bind_the_tweepy_module_name():
    """The subject binds three names *from* tweepy and not tweepy itself.

    This absence is the production fact that makes the ``NameError`` in
    ``start_twitter_stream`` unconditional, and it is asserted here directly
    on the module namespace.
    """
    assert not hasattr(twitter_service, UNIMPORTED_MODULE_NAME)


def test_module_settings_is_an_independent_instance():
    """The subject builds its own ``Settings`` at module scope.

    It is a ``Settings``, and it is not the ``app.core.config`` singleton, so
    replacing it reaches this module alone.
    """
    assert isinstance(twitter_service.settings, config.Settings)
    assert twitter_service.settings is not config.settings


@pytest.mark.parametrize("field_name", UNDECLARED_CONSUMER_FIELDS)
def test_settings_does_not_declare_consumer_field(field_name):
    """``Settings`` declares neither consumer field the subject reads.

    The declared credential fields are ``TWITTER_API_KEY`` and
    ``TWITTER_API_SECRET``.  Neither consumer name is a model field, and
    neither is present on the instance the subject reads.
    """
    assert field_name not in config.Settings.__fields__
    assert not hasattr(twitter_service.settings, field_name)


# ``TwitterStreamListener.on_status``.  Every payload key the listener builds
# is absent from the schema, so validation fails and nothing after it runs.


def test_on_status_raises_validation_error(
    mock_listener, mock_status, mock_add_tweet
):
    """``on_status`` raises rather than returning a value.

    The listener has no early exit and no ``except``, so the pydantic failure
    propagates to the caller -- in production, to tweepy's stream loop.
    """
    with pytest.raises(ValidationError):
        mock_listener.on_status(mock_status)


def test_on_status_does_not_return_true(
    mock_listener, mock_status, mock_add_tweet
):
    """The trailing ``return True`` is unreachable.

    ``outcome`` would be rebound by a completed call, so it still holding
    :data:`UNREACHED` establishes that no value -- ``True`` included -- was
    produced.
    """
    outcome = UNREACHED

    with pytest.raises(ValidationError):
        outcome = mock_listener.on_status(mock_status)

    assert outcome is UNREACHED


def test_on_status_reports_nine_missing_fields(
    mock_listener, mock_status, mock_add_tweet
):
    """Exactly nine errors are reported.

    pydantic v1 ignores keyword arguments naming no field, so the four keys
    the listener supplies add nothing to the count and the total is the
    number of required fields left unsupplied.
    """
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    assert len(excinfo.value.errors()) == MISSING_TWEET_FIELD_COUNT


def test_on_status_names_every_required_schema_field(
    mock_listener, mock_status, mock_add_tweet
):
    """The reported fields are exactly the schema's nine required ones."""
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    reported = {error["loc"][0] for error in excinfo.value.errors()}

    assert reported == set(MISSING_TWEET_FIELDS)


def test_on_status_omits_the_defaulted_schema_field(
    mock_listener, mock_status, mock_add_tweet
):
    """``quoted_tweet_id`` is not reported.

    It is the schema's only field carrying a default, so its absence from
    the payload is not an error.
    """
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    reported = {error["loc"][0] for error in excinfo.value.errors()}

    assert DEFAULTED_TWEET_FIELD not in reported


def test_on_status_reports_only_missing_field_errors(
    mock_listener, mock_status, mock_add_tweet
):
    """Every error is a missing required field and none is a type failure.

    The four keys the listener builds name no field of the schema, so pydantic
    discards all four silently and reports no error against any of them.
    """
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    errors = excinfo.value.errors()

    assert {error["type"] for error in errors} == {MISSING_FIELD_ERROR_TYPE}
    assert {error["msg"] for error in errors} == {MISSING_FIELD_ERROR_MESSAGE}
    assert {len(error["loc"]) for error in errors} == {1}


def test_on_status_validation_error_names_the_tweet_model(
    mock_listener, mock_status, mock_add_tweet
):
    """The failure comes from the schema the subject imported."""
    with pytest.raises(ValidationError) as excinfo:
        mock_listener.on_status(mock_status)

    assert excinfo.value.model is twitter_service.Tweet


def test_on_status_does_not_persist_the_tweet(
    mock_listener, mock_status, mock_add_tweet
):
    """``add_tweet`` is never called.

    Validation precedes the write, so the listener persists nothing on any
    path: there is no status that reaches the call.
    """
    with pytest.raises(ValidationError):
        mock_listener.on_status(mock_status)

    assert mock_add_tweet.call_count == 0


def test_on_status_absent_author_raises_attribute_error(
    mock_listener, mock_add_tweet
):
    """A status with no author fails while the payload is assembled.

    ``on_status`` reads ``status.user.screen_name`` before constructing
    ``Tweet``, so an absent author surfaces as ``AttributeError`` and the
    ``ValidationError`` is never reached.
    """
    with pytest.raises(AttributeError, match=ABSENT_AUTHOR_ERROR):
        mock_listener.on_status(make_status(user=None))

    assert mock_add_tweet.call_count == 0


# ``start_twitter_stream`` with the two undeclared consumer fields supplied.
# Three statements run, then the unbound ``tweepy`` name ends the function.


def test_start_twitter_stream_raises_name_error(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    """The stream starter terminates at the unbound ``tweepy`` name.

    This is the function's terminal state, and the ``stream.filter`` call
    after it -- a blocking live Twitter connection -- is unreachable.
    """
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()


def test_start_twitter_stream_does_not_return(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    """The function has no reachable return."""
    outcome = UNREACHED

    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        outcome = twitter_service.start_twitter_stream()

    assert outcome is UNREACHED


def test_start_twitter_stream_builds_the_oauth_handler(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    """``OAuthHandler`` receives the two consumer values positionally.

    The two values are mutually distinct, so their order in the call
    establishes which settings field each was read from.
    """
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
    """``set_access_token`` receives the two access-token values positionally.

    Called on the object ``OAuthHandler`` returned, which is the ``auth``
    the function goes on to hand to ``API``.
    """
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
    """``API`` receives the authenticated handler itself, not a copy."""
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()

    assert mock_twitter_client.api.call_count == 1
    assert mock_twitter_client.api.call_args[0] == (mock_twitter_client.auth,)
    assert mock_twitter_client.api.call_args[1] == {}


def test_start_twitter_stream_does_not_read_track_keywords(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    """``TWITTER_TRACK_KEYWORDS`` is never read.

    The stand-in does not carry the field, so reaching the ``stream.filter``
    call would raise ``AttributeError`` on the stand-in.  The ``NameError``
    arriving instead establishes that the read never happens.
    """
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()

    assert not hasattr(mock_stream_settings, "TWITTER_TRACK_KEYWORDS")


def test_start_twitter_stream_does_not_persist_a_tweet(
    mock_stream_settings, mock_twitter_client, mock_add_tweet
):
    """No write reaches Firestore.

    The starter constructs a listener but never delivers a status to it, so
    the writer is not called.
    """
    with pytest.raises(NameError, match=UNIMPORTED_MODULE_ERROR):
        twitter_service.start_twitter_stream()

    assert mock_add_tweet.call_count == 0


# ``start_twitter_stream`` in its natural state.  Ordered after the tests
# above, so a forward run reads the subject's real ``Settings`` back.


def test_start_twitter_stream_without_consumer_fields_raises_attribute_error(
    mock_add_tweet,
):
    """Reading the first undeclared consumer field ends the function.

    Nothing is replaced beyond the Firestore writer: the failure happens
    while the first statement's arguments are being evaluated, so no tweepy
    constructor and no network boundary is reachable from here.
    """
    with pytest.raises(AttributeError, match=UNDECLARED_CONSUMER_KEY_FIELD):
        twitter_service.start_twitter_stream()


def test_start_twitter_stream_natural_state_does_not_return(mock_add_tweet):
    """No value is produced in the natural state either."""
    outcome = UNREACHED

    with pytest.raises(AttributeError, match=UNDECLARED_CONSUMER_KEY_FIELD):
        outcome = twitter_service.start_twitter_stream()

    assert outcome is UNREACHED


def test_start_twitter_stream_natural_state_does_not_persist_a_tweet(
    mock_add_tweet,
):
    """No write reaches Firestore in the natural state."""
    with pytest.raises(AttributeError, match=UNDECLARED_CONSUMER_KEY_FIELD):
        twitter_service.start_twitter_stream()

    assert mock_add_tweet.call_count == 0

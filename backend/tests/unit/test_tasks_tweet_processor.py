"""Unit suite for ``app/tasks/tweet_processor.py``, the tweet ingestion chain.

Subject
-------
The module declares two public names.  ``TweetStreamListener`` subclasses
tweepy 3.x's ``StreamListener`` and its ``on_status`` is the ingestion entry
point; the free function ``start_tweet_stream`` wires a tweepy stream onto a
listener instance.  Line 7 constructs a ``Settings()`` of its own at module
scope, so ``tweet_processor.settings`` is an object distinct from
``app.core.config.settings`` carrying the same declared values.

What this suite asserts
-----------------------
* ``TweetStreamListener`` derives from ``tweepy.StreamListener``, and every
  instance carries an ``llm_service``.
* ``on_status`` gates at line 28 on the **sum** of ``retweet_count`` and
  ``favorite_count`` against ``Settings.POPULARITY_THRESHOLD``, with a strict
  ``<``: a sum of 99 is skipped, a sum of 100 is not.  Each side of the
  boundary is probed with the same sum reached through different splits, so
  neither count alone can account for the outcome.
* A status below the gate takes the early ``return True`` at line 29 and
  consults nothing further.
* A status that clears the gate reaches
  ``self.llm_service.calculate_doubt_rating`` exactly once, with the text read
  off the status.
* A status that clears the gate then raises a pydantic ``ValidationError``
  naming exactly eight required fields as missing, every one of them a
  not-supplied error, raised by ``app.schema.tweet.Tweet``.
* ``add_tweet`` is never called, on either side of the boundary, and not even
  when it is armed to fail.
* ``start_tweet_stream`` returns ``None`` and drives ``tweepy.OAuthHandler``,
  ``auth.set_access_token``, ``tweepy.API``, ``tweepy.Stream`` and
  ``stream.filter`` exactly once each with the values the module's own
  ``settings`` carries.  ``Stream`` receives ``auth`` and ``listener`` as
  keyword arguments and nothing positionally, and that ``listener`` is a
  ``TweetStreamListener`` instance.
* ``Settings.DOUBT_RATING_THRESHOLD`` is 0.7, and this module never reads it.

Current behaviour captured as divergence
----------------------------------------
``add_tweet`` has a call count of zero on **every** path.  Below the gate the
listener returns before reaching it; above the gate ``Tweet(...)`` raises
first.  Lines 46 and 48 — the persistence call and the second ``return True``
— are unreachable through any input, so their absence from coverage is a
ceiling and not a gap.

Line 35 builds the ``Tweet`` from ``id``, ``text``, ``user``, ``created_at``,
``retweet_count``, ``favorite_count`` and ``doubt_rating``, while the schema
declares ``tweet_id``, ``content``, ``user_id``, ``timestamp``,
``likes_count``, ``retweets_count``, ``doubt_rating``, ``ai_tools`` and
``media_urls``.  pydantic v1 ignores an undeclared keyword, so the six
mis-named ones are dropped in silence and ``doubt_rating`` is the only one of
the seven that lands.  Eight required fields are left unsupplied, and the
error count is eight.

That count is eight here and nine in
``backend/tests/unit/test_services_twitter.py``: the listener in that module
omits ``doubt_rating`` altogether, whereas this one supplies it and the
``LLMService`` stand-in installed by the ``tweet_processor_module`` fixture is
a ``unittest.mock.MagicMock``, which pydantic coerces to a float.  Two
distinct defects, two distinct counts, each established by execution.

``Settings.DOUBT_RATING_THRESHOLD`` is declared and is read by no production
module anywhere in the repository, so the doubt-rating gate the requirements
describe does not exist.  Line 32 computes a rating and hands it to the
schema; nothing compares it against a threshold.  This suite asserts the
constant and asserts the absence of the reference, and constructs no test of a
gate that is not there.

``TWITTER_CONSUMER_KEY`` and ``TWITTER_CONSUMER_SECRET``, read at line 56, are
declared by no ``Settings`` field — the declared names are ``TWITTER_API_KEY``
and ``TWITTER_API_SECRET`` — so ``start_tweet_stream`` raises
``AttributeError`` unless both are supplied test-side.  ``Settings`` is a
pydantic v1 model and rejects an assignment to an undeclared field, so
:func:`mock_tweepy` injects them through ``monkeypatch.setitem`` on the
instance's ``__dict__``, which pydantic v1 reads attributes from and which
monkeypatch removes again on teardown.

``Settings.TWITTER_TRACK_KEYWORDS`` declares the empty list, so an
unconfigured stream is filtered on ``track=[]`` and tracks nothing.  Both that
declared value and a configured one are asserted.

Two tests are skipped rather than dropped, each recording a legacy assertion
whose production feature is absent: ``on_status`` performs no media handling
and no deduplication.  Each body holds the assertion it would make, so the
skip is a record rather than a silence.

Scope
-----
Every external boundary is replaced.  ``add_tweet`` is patched on *this*
module, which bound the function object at line 2, and ``tweepy`` is replaced
in ``sys.modules`` for the whole of every ``start_tweet_stream`` call: line 53
imports it inside the function body, and the real ``stream.filter`` at line 67
opens a live Twitter connection and does not return.  ``app/db/firestore.py``
itself, the real ``generate_response`` in ``app/services/llm_service.py`` and
the HTTP surface belong to their own suites.

The subject emits no diagnostic output — ``backend/app`` contains no
``logging`` call and this module no ``print`` — so the observable evidence of
a run is the call record on the injected ``tweepy`` stand-in together with
``add_tweet.call_count``, and those are what the assertions read.

Reasoning for every choice in this module: ``docs/testing/DECISION-LOG.md``.
``docs/testing/TRACEABILITY-MATRIX.md`` records the ``test_tasks.py``
functions this suite is the target of: ``test_process_tweet`` and
``test_process_tweet_error_handling`` are rewritten against
``TweetStreamListener.on_status``, and ``test_process_tweet_with_media`` and
``test_process_tweet_deduplication`` become the two skips.
"""

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

# Oracles.  Every value below is read from the subject, from the schema it
# builds, or from the settings the suite runs against.

#: Import path of the settings module :func:`config_module` resolves.  The
#: subject itself is never imported here: it arrives through the
#: ``tweet_processor_module`` fixture in ``backend/tests/conftest.py``, which
#: installs the ``LLMService`` stand-in the import needs.
CONFIG_MODULE = "app.core.config"

#: Value ``Settings.POPULARITY_THRESHOLD`` declares and the gate at line 28
#: compares against.  ``backend/tests/unit/test_core_config.py`` pins it
#: independently, and :func:`test_popularity_threshold_is_the_gate_oracle`
#: asserts the subject's own settings still carries it, so the parametrised
#: matrix below never recomputes the comparison it is probing.
POPULARITY_THRESHOLD = 100

#: Value ``Settings.DOUBT_RATING_THRESHOLD`` declares.  No production module
#: reads it.
DOUBT_RATING_THRESHOLD = 0.7

#: Name of the unreferenced threshold, as it appears in ``app/core/config.py``.
#: :func:`test_doubt_rating_threshold_is_unreferenced_by_the_subject` asserts
#: the subject's source does not contain it.
DOUBT_RATING_THRESHOLD_NAME = "DOUBT_RATING_THRESHOLD"

#: ``Tweet`` fields declared without a default that line 35 leaves unsupplied.
#: ``doubt_rating`` is required too and is the one field of the nine the
#: listener does supply, which is why this set has eight members and not nine.
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

#: pydantic v1 ``type`` of an error raised for a required field that was not
#: supplied.  Every one of the eight carries it.
MISSING_FIELD_ERROR_TYPE = "value_error.missing"

#: Stand-ins for the two settings ``app/core/config.py`` never declares.
#: Neither is a credential, and neither is declared on production ``Settings``.
CONSUMER_KEY = "test-twitter-consumer-key"

CONSUMER_SECRET = "test-twitter-consumer-secret"

#: Values ``backend/tests/conftest.py`` pins for the two access-token settings,
#: which line 57 forwards to ``auth.set_access_token``.
ACCESS_TOKEN = "test-twitter-access-token"

ACCESS_TOKEN_SECRET = "test-twitter-access-token-secret"

#: Value ``Settings.TWITTER_TRACK_KEYWORDS`` declares: the empty list, so an
#: unconfigured stream tracks nothing.  Held as a tuple, and rendered as the
#: list the assertion compares against, so no test can mutate the oracle.
DECLARED_TRACK_KEYWORDS = ()

#: Track list installed by
#: :func:`test_start_tweet_stream_filters_on_configured_track_keywords`, to
#: assert that line 67 forwards whatever ``settings`` carries rather than a
#: constant of its own.
CONFIGURED_TRACK_KEYWORDS = ("copilot", "chatgpt")

#: Message armed on the patched ``add_tweet`` by
#: :func:`test_on_status_validation_error_precedes_the_add_tweet_failure`,
#: carried over from ``backend/tests/test_tasks.py::
#: test_process_tweet_error_handling``.  It never surfaces.
DATABASE_FAILURE_MESSAGE = "Database error"

#: Media URL the skipped media test would assert onto ``Tweet.media_urls``.
#: ``example.invalid`` is reserved by RFC 2606 and resolves nowhere.
MEDIA_URL = "https://example.invalid/media/1.jpg"

# Popularity boundary matrix.  Each case carries its own counts and its
# expected outcome is the test it belongs to, so no test branches on the sum.

#: ``(retweet_count, favorite_count)`` pairs whose sum is below
#: :data:`POPULARITY_THRESHOLD`.  Three sum to 99, the largest value the strict
#: ``<`` still admits, reached through three different splits; the fourth is
#: the floor.
BELOW_THRESHOLD_COUNTS = (
    (50, 49),
    (0, 99),
    (99, 0),
    (0, 0),
)

#: ``(retweet_count, favorite_count)`` pairs whose sum is at or above
#: :data:`POPULARITY_THRESHOLD`.  Three sum to exactly 100 through three
#: different splits, which is the first sum the strict ``<`` rejects; the
#: fourth is one above it.
AT_OR_ABOVE_THRESHOLD_COUNTS = (
    (50, 50),
    (100, 0),
    (0, 100),
    (50, 51),
)


# Fixtures.  Shared infrastructure comes from backend/tests/conftest.py, which
# supplies tweet_processor_module and the autouse credential neutraliser and
# egress guard; the six below are specific to this module.


@pytest.fixture
def config_module():
    """Return the imported ``app.core.config`` module.

    Read only for the settings singleton that carries
    :data:`DOUBT_RATING_THRESHOLD`.  Importing it is safe at any point:
    ``backend/tests/conftest.py`` seeds every required ``Settings`` variable at
    its own module scope, before any test module is collected.
    """
    return importlib.import_module(CONFIG_MODULE)


@pytest.fixture
def mock_add_tweet(tweet_processor_module):
    """Replace ``app.tasks.tweet_processor.add_tweet`` for one test.

    The patch target is the attribute on the *subject* module, which bound the
    function object with ``from app.db.firestore import add_tweet`` at line 2,
    and not ``app.db.firestore.add_tweet``.  Unpatched, the real function
    resolves credentials and reaches Firestore.

    Yields the :class:`unittest.mock.MagicMock` installed in its place; the
    patch is undone when the test ends.
    """
    with patch.object(
        tweet_processor_module, "add_tweet", MagicMock(name="add_tweet")
    ) as mock:
        yield mock


@pytest.fixture
def tweet_stream_listener(tweet_processor_module):
    """Return a fresh ``TweetStreamListener``.

    Construction runs line 14, so ``llm_service`` is a new stand-in built from
    the ``LLMService`` the ``tweet_processor_module`` fixture bound, and no
    call count is shared with another test.
    """
    return tweet_processor_module.TweetStreamListener()


@pytest.fixture
def status_clearing_the_gate():
    """Return a status whose counts sum to exactly the popularity threshold.

    ``retweet_count`` carries the whole sum and ``favorite_count`` is zero, so
    a case built on this fixture clears the gate at line 28 by the smallest
    margin the strict ``<`` allows.
    """
    return make_status(retweet_count=POPULARITY_THRESHOLD, favorite_count=0)


@pytest.fixture
def mock_tweepy(tweet_processor_module, monkeypatch):
    """Bind a ``tweepy`` stand-in and the two undeclared consumer settings.

    Line 53 executes ``import tweepy`` inside ``start_tweet_stream``, so the
    lookup happens at call time and replacing the entry in :data:`sys.modules`
    is what the function resolves.  The real module is restored when the test
    ends.

    ``Settings`` is a pydantic v1 model: its ``__setattr__`` refuses a field
    the model does not declare, and its attribute reads resolve out of the
    instance ``__dict__``.  ``TWITTER_CONSUMER_KEY`` and
    ``TWITTER_CONSUMER_SECRET`` are written into that mapping, and monkeypatch
    clears both keys on teardown.  Production ``Settings`` is not modified, and
    no test after this one can see either name.
    ``docs/testing/DECISION-LOG.md`` carries the reasoning.

    Yields the :class:`unittest.mock.MagicMock` bound as ``tweepy``.
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
    """Call ``start_tweet_stream`` once and return what the call produced.

    The call happens while :func:`mock_tweepy` holds ``sys.modules['tweepy']``,
    so nothing reaches the network.  ``settings.TWITTER_TRACK_KEYWORDS`` is
    left at its declared value.

    :returns: A :class:`types.SimpleNamespace` exposing ``result``, the
        function's return value, and the five stand-ins the wiring assertions
        read: ``tweepy``, ``auth`` from ``OAuthHandler``, ``api`` from ``API``,
        ``stream`` from ``Stream``, and ``listener``, the object line 66 passed
        as the ``listener`` keyword.
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


# TweetStreamListener contract.


def test_tweet_stream_listener_subclasses_tweepy_stream_listener(
    tweet_processor_module,
):
    """``TweetStreamListener`` derives from tweepy's ``StreamListener``.

    Line 1 imports the base class from tweepy, which the 4.x line removed, so
    this assertion is also what fails first if the pinned ``tweepy==3.10.0``
    is not the installed distribution.
    """
    assert issubclass(
        tweet_processor_module.TweetStreamListener, StreamListener
    )


def test_tweet_stream_listener_builds_an_llm_service(tweet_stream_listener):
    """Line 14 leaves an ``llm_service`` on every instance.

    ``LLMService`` is imported from ``app.services.llm_service`` at line 4 and
    is defined by no production module; the ``tweet_processor_module`` fixture
    in ``backend/tests/conftest.py`` installs the stand-in that resolves the
    import and that line 14 then instantiates.
    """
    assert tweet_stream_listener.llm_service is not None


def test_popularity_threshold_is_the_gate_oracle(tweet_processor_module):
    """The subject's own settings carries the threshold the matrix assumes.

    Line 7 builds a ``Settings()`` separate from the one
    ``app/core/config.py`` exposes, and line 28 reads the gate off *that*
    object.  Asserting it here is what keeps the parametrised cases below from
    silently agreeing with a threshold that had moved.
    """
    assert (
        tweet_processor_module.settings.POPULARITY_THRESHOLD
        == POPULARITY_THRESHOLD
    )


# Popularity boundary matrix.  The expected outcome travels with the case: a
# pair listed below the threshold is skipped and a pair at or above it raises,
# so neither test inspects the sum to decide what to assert.


@pytest.mark.parametrize(
    ("retweet_count", "favorite_count"), BELOW_THRESHOLD_COUNTS
)
def test_on_status_skips_below_popularity_threshold(
    tweet_stream_listener, mock_add_tweet, retweet_count, favorite_count
):
    """A status whose counts sum below the threshold takes the early return.

    Line 28 compares ``retweet_count + favorite_count`` against the threshold
    with a strict ``<``, so 99 is still below it however the sum is split.
    Line 29 returns ``True`` and nothing further in ``on_status`` executes,
    which the zero call count on ``add_tweet`` is what demonstrates: the return
    value alone is also what the far side of the boundary would produce if the
    persistence call succeeded.
    """
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
    """A status whose counts reach the threshold raises before persisting.

    A sum of exactly 100 is the first the strict ``<`` at line 28 does not
    admit, and the three splits that reach it are rejected identically, so the
    gate is on the sum rather than on either count.  Clearing the gate leads to
    line 35, where ``Tweet(...)`` raises, so ``add_tweet`` is not called on
    this path either.
    """
    status = make_status(
        retweet_count=retweet_count, favorite_count=favorite_count
    )

    with pytest.raises(ValidationError):
        tweet_stream_listener.on_status(status)

    assert mock_add_tweet.call_count == 0


def test_on_status_requests_a_doubt_rating_for_the_status_text(
    tweet_stream_listener, mock_add_tweet, status_clearing_the_gate
):
    """Clearing the gate reaches the doubt-rating call at line 32.

    The argument is the text line 21 read off the status, forwarded unchanged.
    The rating is computed and handed to the schema at line 42; no production
    code compares it against a threshold.
    """
    with pytest.raises(ValidationError):
        tweet_stream_listener.on_status(status_clearing_the_gate)

    calculate = tweet_stream_listener.llm_service.calculate_doubt_rating
    calculate.assert_called_once_with(status_clearing_the_gate.text)


# The ValidationError raised at line 35.


def test_on_status_validation_error_reports_eight_missing_fields(
    tweet_stream_listener, mock_add_tweet, status_clearing_the_gate
):
    """The error names exactly the eight required fields line 35 omits.

    The listener supplies ``id``, ``text``, ``user``, ``created_at``,
    ``retweet_count``, ``favorite_count`` and ``doubt_rating``.  Of those
    seven, only ``doubt_rating`` is a declared field; pydantic v1 drops the
    other six without complaint because the schema sets no ``extra`` policy.
    What remains unsupplied is the eight names in
    :data:`MISSING_TWEET_FIELDS`, and every one of the eight errors is a
    not-supplied error rather than a type failure.
    """
    with pytest.raises(ValidationError) as excinfo:
        tweet_stream_listener.on_status(status_clearing_the_gate)

    errors = excinfo.value.errors()

    assert len(errors) == len(MISSING_TWEET_FIELDS)
    assert {error["loc"][0] for error in errors} == MISSING_TWEET_FIELDS
    assert {error["type"] for error in errors} == {MISSING_FIELD_ERROR_TYPE}


def test_on_status_validation_error_originates_in_the_tweet_schema(
    tweet_stream_listener, mock_add_tweet, status_clearing_the_gate
):
    """The error is raised by ``app.schema.tweet.Tweet``.

    Which is what makes the eight names above the schema's requirements rather
    than some other model's, and what makes ``doubt_rating``'s absence from
    them evidence that the value line 32 produced was accepted.
    """
    tweet_schema = importlib.import_module("app.schema.tweet")

    with pytest.raises(ValidationError) as excinfo:
        tweet_stream_listener.on_status(status_clearing_the_gate)

    assert excinfo.value.model is tweet_schema.Tweet


# start_tweet_stream wiring.  Every assertion below reads the call record on
# the tweepy stand-in, which is the whole of this module's observable output.


def test_start_tweet_stream_returns_none(started_stream):
    """``start_tweet_stream`` declares no return value.

    Line 67 is the last statement in the function, so the call evaluates to
    ``None`` once the stream has been filtered.
    """
    assert started_stream.result is None


def test_start_tweet_stream_builds_oauth_handler_from_consumer_settings(
    started_stream,
):
    """Line 56 passes the two consumer settings positionally, in order.

    Neither name is declared by ``Settings``; :func:`mock_tweepy` supplies both
    for the duration of the call, and reading them back off the call record is
    what shows line 56 forwards them rather than substituting the declared
    ``TWITTER_API_KEY`` pair.
    """
    started_stream.tweepy.OAuthHandler.assert_called_once_with(
        CONSUMER_KEY, CONSUMER_SECRET
    )


def test_start_tweet_stream_sets_the_access_token_from_settings(
    started_stream,
):
    """Line 57 sets the access token on the handler line 56 returned.

    Both values are declared ``Settings`` fields, pinned by
    ``backend/tests/conftest.py``, and are passed positionally in order.
    """
    started_stream.auth.set_access_token.assert_called_once_with(
        ACCESS_TOKEN, ACCESS_TOKEN_SECRET
    )


def test_start_tweet_stream_builds_the_api_from_the_auth_handler(
    started_stream,
):
    """Line 60 constructs the API object around that same handler."""
    started_stream.tweepy.API.assert_called_once_with(started_stream.auth)


def test_start_tweet_stream_builds_the_stream_with_keyword_arguments_only(
    started_stream,
):
    """Line 66 passes ``auth`` and ``listener`` by keyword and nothing else.

    ``auth`` is the API object's own ``auth`` attribute rather than the handler
    line 56 built, which is asserted by identity.
    """
    call = started_stream.tweepy.Stream.call_args

    assert started_stream.tweepy.Stream.call_count == 1
    assert call.args == ()
    assert set(call.kwargs) == {"auth", "listener"}
    assert call.kwargs["auth"] is started_stream.api.auth


def test_start_tweet_stream_passes_a_tweet_stream_listener(
    tweet_processor_module, started_stream
):
    """Line 63 instantiates the listener line 66 then hands to the stream."""
    assert isinstance(
        started_stream.listener, tweet_processor_module.TweetStreamListener
    )


def test_start_tweet_stream_filters_on_the_declared_track_keywords(
    started_stream,
):
    """Line 67 filters on ``settings.TWITTER_TRACK_KEYWORDS``.

    Its declared value is the empty list, so an unconfigured stream is started
    with ``track=[]`` and tracks nothing at all.
    """
    started_stream.stream.filter.assert_called_once_with(
        track=list(DECLARED_TRACK_KEYWORDS)
    )


def test_start_tweet_stream_filters_on_configured_track_keywords(
    tweet_processor_module, mock_tweepy, monkeypatch
):
    """Line 67 forwards whatever ``TWITTER_TRACK_KEYWORDS`` carries.

    The declared empty list is replaced for the duration of one call, and the
    exact replacement arrives at ``stream.filter``, so line 67 reads the
    setting rather than holding a keyword list of its own.
    """
    monkeypatch.setitem(
        tweet_processor_module.settings.__dict__,
        "TWITTER_TRACK_KEYWORDS",
        list(CONFIGURED_TRACK_KEYWORDS),
    )

    tweet_processor_module.start_tweet_stream()

    mock_tweepy.Stream.return_value.filter.assert_called_once_with(
        track=list(CONFIGURED_TRACK_KEYWORDS)
    )


# Error disposition.  Rewritten from
# backend/tests/test_tasks.py::test_process_tweet_error_handling, whose intent
# was that a persistence failure propagates out of the task.


def test_on_status_validation_error_precedes_the_add_tweet_failure(
    tweet_stream_listener, mock_add_tweet, status_clearing_the_gate
):
    """An armed ``add_tweet`` failure is not what a caller observes.

    ``add_tweet`` is given a failing side effect, and the exception that leaves
    ``on_status`` is still the ``ValidationError`` from line 35: line 46 sits
    after it and is never reached, so the call count stays at zero and the
    armed message never appears.  The legacy intent — that a failure below the
    listener is not swallowed — holds, but the failure a caller sees is the
    schema's and not the database's.
    """
    mock_add_tweet.side_effect = Exception(DATABASE_FAILURE_MESSAGE)

    with pytest.raises(ValidationError) as excinfo:
        tweet_stream_listener.on_status(status_clearing_the_gate)

    assert mock_add_tweet.call_count == 0
    assert DATABASE_FAILURE_MESSAGE not in str(excinfo.value)


# Legacy stubs whose production feature does not exist.  Each body holds the
# assertion it would make, and each reason names what is absent.


@pytest.mark.skip(
    reason="app/tasks/tweet_processor.py implements no media handling. "
    "on_status reads only id_str, text, user.screen_name, created_at, "
    "retweet_count and favorite_count off a status (lines 20-25) and never "
    "entities or extended_entities, and line 35 leaves Tweet.media_urls "
    "unsupplied, which is one of the eight fields the ValidationError names. "
    "Replaces backend/tests/test_tasks.py::test_process_tweet_with_media."
)
def test_on_status_with_media(tweet_stream_listener, mock_add_tweet):
    """``on_status`` would carry a status's media URLs onto the tweet.

    The assertion this test makes once media handling exists: a status
    carrying a media entity is persisted as a ``Tweet`` whose ``media_urls``
    holds that URL.
    """
    status = make_status(
        retweet_count=POPULARITY_THRESHOLD,
        favorite_count=0,
        extended_entities={"media": [{"media_url_https": MEDIA_URL}]},
    )

    assert tweet_stream_listener.on_status(status) is True

    mock_add_tweet.assert_called_once()
    assert mock_add_tweet.call_args.args[0].media_urls == [MEDIA_URL]


@pytest.mark.skip(
    reason="app/tasks/tweet_processor.py implements no deduplication. "
    "on_status neither reads a tweet back through app.db.firestore.get_tweet "
    "nor consults any record of seen ids before line 46, so one status "
    "delivered twice would be written twice; tweepy 3.x also offers the "
    "listener no delivery-once guarantee. Replaces "
    "backend/tests/test_tasks.py::test_process_tweet_deduplication."
)
def test_on_status_deduplication(tweet_stream_listener, mock_add_tweet):
    """``on_status`` would persist a repeated status only once.

    The assertion this test makes once deduplication exists: delivering the
    same status twice leaves one write behind, and the second delivery still
    reports success to the stream.
    """
    status = make_status(retweet_count=POPULARITY_THRESHOLD, favorite_count=0)

    assert tweet_stream_listener.on_status(status) is True
    assert tweet_stream_listener.on_status(status) is True

    assert mock_add_tweet.call_count == 1


# The doubt-rating threshold, which is configuration and nothing more.


def test_doubt_rating_threshold_is_declared_configuration(config_module):
    """``Settings.DOUBT_RATING_THRESHOLD`` is 0.7 on the settings singleton."""
    assert config_module.settings.DOUBT_RATING_THRESHOLD == pytest.approx(
        DOUBT_RATING_THRESHOLD
    )


def test_doubt_rating_threshold_is_unreferenced_by_the_subject(
    tweet_processor_module,
):
    """The subject's source does not contain the threshold's name.

    Line 32 computes a doubt rating and line 42 hands it to the schema; no
    statement compares it against anything.  The gate the requirements describe
    is therefore absent from the module that would own it, and the constant is
    assertable as configuration only.
    """
    source = inspect.getsource(tweet_processor_module)

    assert DOUBT_RATING_THRESHOLD_NAME not in source

"""Deterministic test-data builders for the Code Skeptic Scanner backend suite.

Every backend unit and integration suite draws its payloads from this module.
Each builder constructs its result from the literal defaults declared below and
applies the keyword ``overrides`` last, so a caller restates only the fields a
case actually varies.

This module imports nothing but the standard library, declares no pytest
fixture, and performs no I/O, no logging and no clock read.

Catalogue
---------
:func:`make_tweet`
    ``dict`` carrying the ten fields ``app/schema/tweet.py`` declares.
    ``Tweet(**make_tweet())`` constructs; ``backend/tests/unit/test_schema.py``
    is the gate that keeps it so.
:func:`make_response`
    ``dict`` keyed ``tweet_id``, ``response``, ``generated_at``.  The first two
    mirror the ``add_response(tweet_id, response_content)`` call at
    ``app/tasks/response_generator.py`` line 18 and the ``{"response": ...}``
    body returned by ``app/api/routes/tweets.py`` line 36.  The repository
    declares no response schema; the shape claims conformance to none.
:func:`make_analytics_row`
    ``dict`` shaped as one BigQuery result row, keyed on the SQL *aliases* that
    ``app/services/analytics_service.py`` selects and then indexes:
    ``date``/``tweet_count``/``avg_retweets``/``avg_favorites`` for
    ``get_tweet_analytics``, and
    ``date``/``active_users``/``avg_followers``/``avg_friends`` for
    ``get_user_analytics``.  ``retweet_count`` and ``favorite_count`` are
    arguments to ``AVG()`` inside the query text and are not row keys.
:func:`make_status`
    :class:`types.SimpleNamespace` duck-typing the tweepy status that
    ``app/tasks/tweet_processor.py`` lines 20-25 and
    ``app/services/twitter_service.py`` lines 18-21 read by attribute.

Determinism
-----------
Every default is a literal, and two no-argument calls to any builder compare
equal.  Every builder returns freshly constructed containers, so no test can
affect another by mutating a value it was handed.
"""

from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "make_tweet",
    "make_response",
    "make_analytics_row",
    "make_status",
    "FIRST_ANALYTICS_DATE",
    "SECOND_ANALYTICS_DATE",
    "ANALYTICS_ROW_KINDS",
]

# --------------------------------------------------------------------------- #
# Tweet payload defaults.  Field names and types are those declared by
# ``app/schema/tweet.py``: nine required fields plus ``quoted_tweet_id``, whose
# declared default is ``None``.
# --------------------------------------------------------------------------- #

#: ``tweet_id`` of a tweet payload and ``id_str`` of a status.
DEFAULT_TWEET_ID: str = "1234567890"

#: ``content`` of a tweet payload and ``text`` of a status.
DEFAULT_TWEET_CONTENT: str = "This is a test tweet"

#: ``user_id`` of a tweet payload.
DEFAULT_USER_ID: str = "test_user"

#: ``user.screen_name`` of a status.
DEFAULT_SCREEN_NAME: str = "test_user"

#: ``timestamp`` of a tweet payload and ``created_at`` of a status.  A
#: :class:`datetime.datetime`, the type ``Tweet.timestamp`` declares.
DEFAULT_TIMESTAMP: datetime = datetime(2024, 1, 1, 0, 0, 0)

#: ``likes_count`` of a tweet payload.
DEFAULT_LIKES_COUNT: int = 120

#: ``retweets_count`` of a tweet payload.
DEFAULT_RETWEETS_COUNT: int = 45

#: ``doubt_rating`` of a tweet payload.  A ``float`` greater than the
#: ``Settings.DOUBT_RATING_THRESHOLD`` of ``0.7``.
DEFAULT_DOUBT_RATING: float = 0.75

#: Source of the ``ai_tools`` list.  A tuple; :func:`make_tweet` copies it.
DEFAULT_AI_TOOLS: Tuple[str, ...] = ("GitHub Copilot", "ChatGPT")

#: Source of the ``media_urls`` list.  ``example.invalid`` is reserved by
#: RFC 2606 and resolves nowhere.
DEFAULT_MEDIA_URLS: Tuple[str, ...] = (
    "https://example.invalid/media/1.jpg",
)

#: ``quoted_tweet_id`` of a tweet payload, matching the schema's own default.
DEFAULT_QUOTED_TWEET_ID: Optional[str] = None

# --------------------------------------------------------------------------- #
# Generated-response defaults.
# --------------------------------------------------------------------------- #

#: ``response`` of a generated-response payload.
DEFAULT_RESPONSE_CONTENT: str = "This is a test response"

#: ``generated_at`` of a generated-response payload; fifteen minutes after
#: :data:`DEFAULT_TIMESTAMP`.
DEFAULT_GENERATED_AT: datetime = datetime(2024, 1, 1, 0, 15, 0)

# --------------------------------------------------------------------------- #
# Analytics row defaults.
#
# ``get_tweet_analytics`` reduces its rows to ``int(df['tweet_count'].sum())``,
# ``float(df['tweet_count'].mean())``, ``float(df['avg_retweets'].mean())``
# and ``float(df['avg_favorites'].mean())``.  Pairing the ``"tweet"`` default
# with a second row overriding ``tweet_count=5``, ``avg_retweets=2.0``,
# ``avg_favorites=4.0`` and ``date=SECOND_ANALYTICS_DATE`` yields
# ``total_tweets == 8``, ``avg_daily_tweets == 4.0``, ``avg_retweets == 1.5``,
# ``avg_favorites == 3.0`` and a two-record ``daily_breakdown``.  The
# ``"user"`` shape is numerically identical under ``active_users``,
# ``avg_followers`` and ``avg_friends``.
# --------------------------------------------------------------------------- #

#: ``date`` of the default row, and the ``start_date`` that puts
#: ``BETWEEN '2024-01-01' AND '2024-01-02'`` in the emitted SQL.
FIRST_ANALYTICS_DATE: str = "2024-01-01"

#: ``date`` of the second row of the pair, and the matching ``end_date``.
SECOND_ANALYTICS_DATE: str = "2024-01-02"

#: Row templates as ordered ``(key, value)`` pairs.  Insertion order is the
#: ``SELECT`` order, which is the column order pandas gives the ``DataFrame``
#: and therefore the key order of each ``daily_breakdown`` record.
_ANALYTICS_ROW_TEMPLATES: Dict[str, Tuple[Tuple[str, Any], ...]] = {
    "tweet": (
        ("date", FIRST_ANALYTICS_DATE),
        ("tweet_count", 3),
        ("avg_retweets", 1.0),
        ("avg_favorites", 2.0),
    ),
    "user": (
        ("date", FIRST_ANALYTICS_DATE),
        ("active_users", 3),
        ("avg_followers", 1.0),
        ("avg_friends", 2.0),
    ),
}

#: The ``kind`` values :func:`make_analytics_row` accepts.
ANALYTICS_ROW_KINDS: Tuple[str, ...] = tuple(sorted(_ANALYTICS_ROW_TEMPLATES))

# --------------------------------------------------------------------------- #
# Status defaults.
# --------------------------------------------------------------------------- #

#: ``retweet_count`` of a status.  With :data:`DEFAULT_FAVORITE_COUNT` the sum
#: is 20, below the ``Settings.POPULARITY_THRESHOLD`` of 100 that
#: ``app/tasks/tweet_processor.py`` line 28 compares against, so an
#: un-overridden status takes that method's early ``return True``.
DEFAULT_RETWEET_COUNT: int = 10

#: ``favorite_count`` of a status.
DEFAULT_FAVORITE_COUNT: int = 10

#: Sentinel distinguishing an omitted keyword from one passed as ``None``.
_UNSET: Any = object()


def make_tweet(**overrides: Any) -> Dict[str, Any]:
    """Return a tweet payload satisfying ``app/schema/tweet.py``.

    The returned ``dict`` carries all ten declared fields:
    ``tweet_id``, ``content``, ``user_id``, ``timestamp``, ``likes_count``,
    ``retweets_count``, ``doubt_rating``, ``ai_tools``, ``media_urls`` and
    ``quoted_tweet_id``.  ``timestamp`` is a :class:`datetime.datetime`;
    ``ai_tools`` and ``media_urls`` are non-empty lists of ``str``, freshly
    copied on every call; ``doubt_rating`` is a ``float``.

    ``Tweet(**make_tweet())`` constructs, and so does
    ``Tweet(**make_tweet(quoted_tweet_id=None))``.  Removing any of the nine
    required keys raises a pydantic ``ValidationError``, which is how the edge
    cases of ``backend/tests/unit/test_schema.py`` are produced.

    :param overrides: Keys applied after the defaults.  A key absent from the
        schema is placed in the result unchanged.
    :returns: A new ``dict`` sharing no mutable object with any other call.

    Usage::

        make_tweet()                                # schema-valid payload
        make_tweet(doubt_rating=0.9)                # one field varied
        payload = make_tweet(); del payload["content"]   # rejection case
    """
    payload: Dict[str, Any] = {
        "tweet_id": DEFAULT_TWEET_ID,
        "content": DEFAULT_TWEET_CONTENT,
        "user_id": DEFAULT_USER_ID,
        "timestamp": DEFAULT_TIMESTAMP,
        "likes_count": DEFAULT_LIKES_COUNT,
        "retweets_count": DEFAULT_RETWEETS_COUNT,
        "doubt_rating": DEFAULT_DOUBT_RATING,
        "ai_tools": list(DEFAULT_AI_TOOLS),
        "media_urls": list(DEFAULT_MEDIA_URLS),
        "quoted_tweet_id": DEFAULT_QUOTED_TWEET_ID,
    }
    payload.update(overrides)
    return payload


def make_response(**overrides: Any) -> Dict[str, Any]:
    """Return a generated-response payload.

    The returned ``dict`` carries ``tweet_id``, ``response`` and
    ``generated_at``.  ``tweet_id`` and ``response`` are the two values
    ``app/tasks/response_generator.py`` line 18 passes to
    ``add_response(tweet_id, response_content)``, and ``response`` is the body
    key ``app/api/routes/tweets.py`` line 36 returns.  ``generated_at`` is a
    :class:`datetime.datetime`.

    The repository declares no response schema; no model validates this shape
    and it asserts conformance to none.

    :param overrides: Keys applied after the defaults.
    :returns: A new ``dict`` sharing no mutable object with any other call.

    Usage::

        make_response()
        make_response(response="Generated response")
    """
    payload: Dict[str, Any] = {
        "tweet_id": DEFAULT_TWEET_ID,
        "response": DEFAULT_RESPONSE_CONTENT,
        "generated_at": DEFAULT_GENERATED_AT,
    }
    payload.update(overrides)
    return payload


def make_analytics_row(
    kind: str = "tweet", **overrides: Any
) -> Dict[str, Any]:
    """Return one BigQuery result row for the analytics service.

    The reader is ``app/services/analytics_service.py``.
    ``kind="tweet"`` returns the row ``get_tweet_analytics`` consumes, keyed
    ``date``, ``tweet_count``, ``avg_retweets``, ``avg_favorites``.
    ``kind="user"`` returns the row ``get_user_analytics`` consumes, keyed
    ``date``, ``active_users``, ``avg_followers``, ``avg_friends``.  Both key
    sets are the ``as`` aliases of the ``SELECT`` list, which are the names the
    service indexes on the ``DataFrame``.

    ``date`` is a ``str``.  Feeding a list of these rows through
    ``pandas.DataFrame`` reproduces the aggregation exactly; feeding an *empty*
    list produces a column-less frame, so the service's ``KeyError`` cases are
    reached by omitting rows and never by dropping a key.

    :param kind: ``"tweet"`` or ``"user"``.  Bound by name, so it never reaches
        the returned row.  See :data:`ANALYTICS_ROW_KINDS`.
    :param overrides: Keys applied after the defaults.
    :raises ValueError: If ``kind`` is not one of :data:`ANALYTICS_ROW_KINDS`.
    :returns: A new ``dict`` sharing no mutable object with any other call.

    Usage::

        rows = [
            make_analytics_row(),
            make_analytics_row(
                date=SECOND_ANALYTICS_DATE,
                tweet_count=5,
                avg_retweets=2.0,
                avg_favorites=4.0,
            ),
        ]
        # total_tweets 8, avg_daily_tweets 4.0,
        # avg_retweets 1.5, avg_favorites 3.0
    """
    template = _ANALYTICS_ROW_TEMPLATES.get(kind)
    if template is None:
        raise ValueError(
            "make_analytics_row() received kind={kind!r}; the supported kinds "
            "are {kinds}.".format(
                kind=kind,
                kinds=", ".join(repr(name) for name in ANALYTICS_ROW_KINDS),
            )
        )
    row: Dict[str, Any] = dict(template)
    row.update(overrides)
    return row


def make_status(**overrides: Any) -> SimpleNamespace:
    """Return a duck object standing in for a tweepy status.

    The result exposes ``id_str``, ``text``, ``user``, ``created_at``,
    ``retweet_count`` and ``favorite_count`` as *attributes*, which is how both
    listeners read a status: ``app/tasks/tweet_processor.py`` lines 20-25 read
    all six, and ``app/services/twitter_service.py`` lines 18-21 read
    ``id_str``, ``text``, ``user.screen_name`` and ``created_at``.  ``user`` is
    itself a :class:`types.SimpleNamespace` carrying ``screen_name``, and
    ``created_at`` is a :class:`datetime.datetime`.

    ``retweet_count`` and ``favorite_count`` are independently overridable,
    which is what the popularity matrix varies against the
    ``Settings.POPULARITY_THRESHOLD`` of 100 that
    ``app/tasks/tweet_processor.py`` line 28 compares their *sum* against:
    ``(50, 49)``, ``(0, 99)`` and ``(99, 0)`` sum to 99 and fall below the
    gate, while ``(50, 50)`` and ``(50, 51)`` clear it.

    :param overrides: Attributes applied after the defaults.  ``screen_name``
        is lifted onto a new nested ``user``.  ``user`` replaces the nested
        object outright, including when passed as ``None``.  Any other key
        becomes an additional attribute.
    :raises TypeError: If both ``user`` and ``screen_name`` are supplied.
    :returns: A new :class:`types.SimpleNamespace`, nested object included,
        sharing no mutable object with any other call.

    Usage::

        make_status(retweet_count=50, favorite_count=49)   # below the gate
        make_status(retweet_count=50, favorite_count=50)   # clears the gate
        make_status(screen_name="skeptic")                 # nested attribute
        make_status(user=None)                             # absent author
    """
    user = overrides.pop("user", _UNSET)
    if "screen_name" in overrides:
        screen_name = overrides.pop("screen_name")
        if user is not _UNSET:
            raise TypeError(
                "make_status() received both 'user' and 'screen_name'; pass "
                "'screen_name' to set the nested author, or 'user' to replace "
                "the nested object outright."
            )
        user = SimpleNamespace(screen_name=screen_name)
    elif user is _UNSET:
        user = SimpleNamespace(screen_name=DEFAULT_SCREEN_NAME)

    attributes: Dict[str, Any] = {
        "id_str": DEFAULT_TWEET_ID,
        "text": DEFAULT_TWEET_CONTENT,
        "created_at": DEFAULT_TIMESTAMP,
        "retweet_count": DEFAULT_RETWEET_COUNT,
        "favorite_count": DEFAULT_FAVORITE_COUNT,
    }
    attributes.update(overrides)
    return SimpleNamespace(user=user, **attributes)

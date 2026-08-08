"""Unit suite for ``app/services/analytics_service.py``, the two BigQuery
date-ranged aggregations.

The subject declares two public functions, ``get_tweet_analytics(start_date,
end_date)`` and ``get_user_analytics(start_date, end_date)``.  Each assembles a
SQL string, hands it to ``run_query``, wraps the returned rows in a pandas
``DataFrame`` and reduces that frame to a dictionary of totals, averages and a
per-day breakdown.

Patch boundary
--------------
Every test replaces ``app.services.analytics_service.run_query`` -- the
attribute on the *subject* module, which bound the name at import time with
``from app.db.bigquery import run_query`` (line 2).  No test replaces
``app.db.bigquery.run_query``.
:func:`test_run_query_is_bound_into_the_subject_module` and
:func:`test_mock_run_query_replaces_the_subject_module_attribute` assert
the two halves of that binding directly: the name resolves to the same
object under both modules before a patch, and to the replacement on the
subject alone during one.
Because the boundary sits above ``app.db.bigquery``, no BigQuery client is
constructed and no credential is read by any test in this module.

What this suite asserts
-----------------------
* The module exposes ``get_tweet_analytics`` and ``get_user_analytics`` and
  nothing else callable; ``AnalyticsService`` and ``calculate_engagement_rate``
  are absent.
* ``get_tweet_analytics`` reduces two controlled rows to ``total_tweets`` 8,
  ``avg_daily_tweets`` 4.0, ``avg_retweets`` 1.5, ``avg_favorites`` 3.0 and a
  two-record ``daily_breakdown``.
* ``get_user_analytics`` reduces two controlled rows to
  ``total_active_users`` 8, ``avg_daily_active_users`` 4.0, ``avg_followers``
  1.5, ``avg_friends`` 3.0 and a two-record ``daily_breakdown``.
* Each function returns exactly its five declared keys, asserted by set
  equality, with the total coerced to ``int`` and the three averages to
  ``float``.
* ``daily_breakdown`` is the ``DataFrame.to_dict('records')`` shape: a list of
  plain dictionaries keyed on the row keys, equal to the rows that went in.
* Each function issues exactly one query, as a single positional argument.
* The emitted SQL carries the ``BETWEEN`` clause built from the caller's two
  date strings, the ``as`` aliases of the ``SELECT`` list, and the dataset from
  ``settings.BIGQUERY_DATASET``.  Assertions are substring containment; the
  query is never rebuilt.

Current behaviour captured as divergence
----------------------------------------
An empty result set raises ``KeyError``.  ``DataFrame([])`` carries no columns,
so the first subscript fails: ``'tweet_count'`` for ``get_tweet_analytics`` and
``'active_users'`` for ``get_user_analytics``.  Neither function returns a
zeroed result and neither raises a domain error.

Propagation is total.  The subject contains no ``try`` and no ``except``, so
anything ``run_query`` raises leaves the function unchanged.  This is the
opposite disposition to ``update_tweet`` in ``app/db/firestore.py``, which
swallows a write failure and returns ``False``.

Neither function validates its date range.  An inverted range and a string that
is not a date are both interpolated verbatim into the SQL text and the call
succeeds.

``get_user_analytics`` returns ``total_active_users``.  The key
``total_users`` -- asserted by legacy
``tests/test_api.py::test_get_user_analytics`` against a
``GET /analytics/users`` route that does not exist -- is absent, and
:func:`test_get_user_analytics_omits_the_legacy_total_users_key` asserts that
absence.

The row keys are the ``as`` aliases of the ``SELECT`` list, not the columns
``AVG()`` reduces: a tweet row is keyed ``date``, ``tweet_count``,
``avg_retweets``, ``avg_favorites``, and carries no ``retweet_count`` or
``favorite_count``.  Every row in this module comes from
``tests.factories.make_analytics_row``, which is the single published source of
both shapes.

Observability
-------------
The subject emits no log record and no diagnostic output, so there is nothing
for ``caplog`` or ``capsys`` to capture and neither is used.  The one
externally visible trace of what the service did is the SQL text handed to
``run_query``; this suite captures it from the replacement's call arguments and
asserts against it.

Scope
-----
``run_query`` itself, the ``Settings.GOOGLE_CLOUD_PROJECT`` class-attribute
access it performs and the BigQuery client it builds belong to
``tests/unit/test_db_bigquery.py``.  The ``bigquery_settings`` fixture is
therefore not requested here: with the boundary above ``app.db.bigquery``,
nothing in this module needs it.

Reasoning for every choice in this module is recorded in
``docs/testing/DECISION-LOG.md``; the legacy constructs it covers are rows E7,
E8, E17 and E18 of ``docs/testing/TRACEABILITY-MATRIX.md``.
"""

from unittest.mock import patch

import pytest

import app.db.bigquery as bigquery
import app.services.analytics_service as analytics_service
from tests.factories import (
    FIRST_ANALYTICS_DATE,
    SECOND_ANALYTICS_DATE,
    make_analytics_row,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Oracles.  Every value below is either read from the subject module or drives
# an aggregation that lands on an exact literal.
# --------------------------------------------------------------------------- #

#: Attribute replaced by :func:`mock_run_query`.  The subject module, never
#: ``app.db.bigquery``.
RUN_QUERY_TARGET = "app.services.analytics_service.run_query"

#: Names the subject module must expose as callables.
PUBLIC_AGGREGATIONS = ("get_tweet_analytics", "get_user_analytics")

#: Names legacy ``tests/test_services.py`` referenced on this module and that
#: production never defined: the class its ``setUp`` instantiated and the
#: method its removed assertions called.
ABSENT_LEGACY_NAMES = ("AnalyticsService", "calculate_engagement_rate")

#: Key legacy ``tests/test_api.py::test_get_user_analytics`` expected from
#: ``GET /analytics/users``.  ``get_user_analytics`` returns
#: ``total_active_users`` instead.
LEGACY_USER_TOTAL_KEY = "total_users"

TWEET_ANALYTICS_KEYS = frozenset(
    {
        "total_tweets",
        "avg_daily_tweets",
        "avg_retweets",
        "avg_favorites",
        "daily_breakdown",
    }
)

USER_ANALYTICS_KEYS = frozenset(
    {
        "total_active_users",
        "avg_daily_active_users",
        "avg_followers",
        "avg_friends",
        "daily_breakdown",
    }
)

# Second-row values.  Paired with the factory defaults -- 3 for the count, 1.0
# and 2.0 for the two averages -- they give a count summing to 8 with a mean of
# 4.0, and averages meaning 1.5 and 3.0.  Each is an exact binary fraction, and
# every assertion below compares with ``==``.

SECOND_ROW_COUNT = 5

SECOND_ROW_FIRST_AVERAGE = 2.0

SECOND_ROW_SECOND_AVERAGE = 4.0

EXPECTED_TOTAL = 8

EXPECTED_DAILY_MEAN = 4.0

EXPECTED_FIRST_AVERAGE = 1.5

EXPECTED_SECOND_AVERAGE = 3.0

EXPECTED_BREAKDOWN_LENGTH = 2

#: ``as`` aliases of the tweet ``SELECT`` list, in the order the subject
#: declares them.  These are the keys a tweet row must carry.
TWEET_QUERY_ALIASES = (
    "as date",
    "as tweet_count",
    "as avg_retweets",
    "as avg_favorites",
)

#: ``as`` aliases of the user ``SELECT`` list.
USER_QUERY_ALIASES = (
    "as date",
    "as active_users",
    "as avg_followers",
    "as avg_friends",
)

#: Message carried by the exception the propagation tests inject.
QUERY_FAILURE_MESSAGE = "query failed"

#: Start of the inverted range: the last day of the year whose first day is
#: :data:`FIRST_ANALYTICS_DATE`.  The end therefore precedes the start by
#: nearly a year.
INVERTED_START_DATE = "2024-12-31"

#: Date pairs neither function validates.  ``inverted`` puts the later date
#: first; ``malformed`` is not a date in any format.
UNVALIDATED_DATE_RANGES = (
    pytest.param(INVERTED_START_DATE, FIRST_ANALYTICS_DATE, id="inverted"),
    pytest.param("not-a-date", "also-not-a-date", id="malformed"),
)


def _tweet_rows():
    """Return the two tweet rows the happy-path oracles are computed from.

    Built from :func:`tests.factories.make_analytics_row`; the first row is the
    factory default and the second varies the date and all three metrics.
    """
    return [
        make_analytics_row(),
        make_analytics_row(
            date=SECOND_ANALYTICS_DATE,
            tweet_count=SECOND_ROW_COUNT,
            avg_retweets=SECOND_ROW_FIRST_AVERAGE,
            avg_favorites=SECOND_ROW_SECOND_AVERAGE,
        ),
    ]


def _user_rows():
    """Return the two user rows the happy-path oracles are computed from.

    The counterpart of :func:`_tweet_rows` for ``kind="user"``, carrying the
    same numeric values under the aliases ``get_user_analytics`` indexes.
    """
    return [
        make_analytics_row(kind="user"),
        make_analytics_row(
            kind="user",
            date=SECOND_ANALYTICS_DATE,
            active_users=SECOND_ROW_COUNT,
            avg_followers=SECOND_ROW_FIRST_AVERAGE,
            avg_friends=SECOND_ROW_SECOND_AVERAGE,
        ),
    ]


def _emitted_query(mock_run_query):
    """Return the SQL text ``run_query`` received, asserting the call shape.

    The subject calls ``run_query(query)`` with one positional argument and no
    keywords; this helper pins that shape before handing back the argument, so
    a caller asserting on the text cannot silently read a different call.
    """
    assert mock_run_query.call_count == 1
    positional, keyword = mock_run_query.call_args
    assert keyword == {}
    assert len(positional) == 1
    return positional[0]


# --------------------------------------------------------------------------- #
# Fixtures.  Shared infrastructure -- the synthetic settings, the credential
# neutraliser and the egress guard -- comes from backend/tests/conftest.py.
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_run_query():
    """Replace ``app.services.analytics_service.run_query`` for one test.

    Yields the replacement, on which a test sets ``return_value`` to the rows
    the aggregation should see or ``side_effect`` to the failure it should
    propagate.  The patch is undone when the test ends, so no module state
    outlives a test and no test depends on another's ordering.
    """
    with patch(RUN_QUERY_TARGET) as replacement:
        yield replacement


@pytest.fixture
def mock_run_query_returning_tweet_rows(mock_run_query):
    """Yield :func:`mock_run_query` already returning :func:`_tweet_rows`."""
    mock_run_query.return_value = _tweet_rows()
    return mock_run_query


@pytest.fixture
def mock_run_query_returning_user_rows(mock_run_query):
    """Yield :func:`mock_run_query` already returning :func:`_user_rows`."""
    mock_run_query.return_value = _user_rows()
    return mock_run_query


# --------------------------------------------------------------------------- #
# Module contract.  What the subject exposes, and what legacy tests referenced
# on it that production never defined.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", PUBLIC_AGGREGATIONS)
def test_module_exposes_aggregation(name):
    """Each declared aggregation is present on the module and callable."""
    assert callable(getattr(analytics_service, name))


@pytest.mark.parametrize("name", ABSENT_LEGACY_NAMES)
def test_module_does_not_expose_legacy_name(name):
    """``AnalyticsService`` and ``calculate_engagement_rate`` are absent.

    Legacy ``tests/test_services.py`` instantiated ``AnalyticsService()`` in
    ``setUp`` and called ``calculate_engagement_rate`` on the result.  The
    module defines neither; rows E17 and E18 of
    ``docs/testing/TRACEABILITY-MATRIX.md`` record their disposition.
    """
    assert not hasattr(analytics_service, name)


def test_run_query_is_bound_into_the_subject_module():
    """``run_query`` resolves to one object under both module names.

    ``app/services/analytics_service.py`` line 2 is
    ``from app.db.bigquery import run_query``, so the subject holds its own
    reference to the function ``app.db.bigquery`` defines.
    """
    assert analytics_service.run_query is bigquery.run_query


def test_mock_run_query_replaces_the_subject_module_attribute(mock_run_query):
    """The fixture rebinds the name on the subject and leaves the other alone.

    While the patch is active the subject resolves ``run_query`` to the
    replacement, and ``app.db.bigquery.run_query`` still resolves to the real
    function -- so nothing this suite calls can reach it.
    """
    assert analytics_service.run_query is mock_run_query
    assert bigquery.run_query is not mock_run_query


# --------------------------------------------------------------------------- #
# get_tweet_analytics -- happy path.
# --------------------------------------------------------------------------- #


def test_get_tweet_analytics_totals_the_tweet_counts(
    mock_run_query_returning_tweet_rows,
):
    """``total_tweets`` is the sum of the rows' ``tweet_count``.

    The two rows carry 3 and 5, so the sum is 8 and the mean is 4.0; the two
    values differ, which is what distinguishes a sum from an average.
    """
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["total_tweets"] == EXPECTED_TOTAL


def test_get_tweet_analytics_averages_the_daily_tweet_counts(
    mock_run_query_returning_tweet_rows,
):
    """``avg_daily_tweets`` is the mean of the rows' ``tweet_count``."""
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_daily_tweets"] == EXPECTED_DAILY_MEAN


def test_get_tweet_analytics_averages_the_retweet_averages(
    mock_run_query_returning_tweet_rows,
):
    """``avg_retweets`` is the mean of the rows' ``avg_retweets``."""
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_retweets"] == EXPECTED_FIRST_AVERAGE


def test_get_tweet_analytics_averages_the_favorite_averages(
    mock_run_query_returning_tweet_rows,
):
    """``avg_favorites`` is the mean of the rows' ``avg_favorites``."""
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_favorites"] == EXPECTED_SECOND_AVERAGE


def test_get_tweet_analytics_returns_the_declared_key_set(
    mock_run_query_returning_tweet_rows,
):
    """The result carries exactly its five declared keys.

    Asserted by set equality, so an added, dropped or renamed key fails.
    """
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert set(result) == set(TWEET_ANALYTICS_KEYS)


def test_get_tweet_analytics_coerces_the_metric_types(
    mock_run_query_returning_tweet_rows,
):
    """The total is an ``int`` and the three averages are ``float``.

    The subject coerces each explicitly, so no numpy scalar reaches a caller.
    Each assertion is on the exact type, so a ``bool`` does not satisfy the
    ``int`` one.
    """
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert type(result["total_tweets"]) is int
    assert type(result["avg_daily_tweets"]) is float
    assert type(result["avg_retweets"]) is float
    assert type(result["avg_favorites"]) is float


def test_get_tweet_analytics_daily_breakdown_is_records_shaped(
    mock_run_query_returning_tweet_rows,
):
    """``daily_breakdown`` is a list of plain dicts equal to the rows.

    ``DataFrame.to_dict('records')`` yields one dictionary per row keyed on the
    frame's columns, which are the row keys; no frame or numpy container
    reaches a caller.
    """
    expected_rows = _tweet_rows()

    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )
    breakdown = result["daily_breakdown"]

    assert type(breakdown) is list
    assert len(breakdown) == EXPECTED_BREAKDOWN_LENGTH
    assert all(type(record) is dict for record in breakdown)
    assert [set(record) for record in breakdown] == [
        set(row) for row in expected_rows
    ]
    assert breakdown == expected_rows


def test_get_tweet_analytics_runs_exactly_one_query(
    mock_run_query_returning_tweet_rows,
):
    """One query is issued, as a single positional argument."""
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    _emitted_query(mock_run_query_returning_tweet_rows)


def test_get_tweet_analytics_emits_the_requested_date_range(
    mock_run_query_returning_tweet_rows,
):
    """The emitted SQL carries the caller's dates in a ``BETWEEN`` clause."""
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _emitted_query(mock_run_query_returning_tweet_rows)

    assert (
        "BETWEEN '{start}' AND '{end}'".format(
            start=FIRST_ANALYTICS_DATE, end=SECOND_ANALYTICS_DATE
        )
        in query
    )


@pytest.mark.parametrize("alias", TWEET_QUERY_ALIASES)
def test_get_tweet_analytics_emits_the_selected_alias(
    alias, mock_run_query_returning_tweet_rows
):
    """Each ``as`` alias the subject then indexes appears in the emitted SQL.

    The aliases are the row contract: ``tweet_count``, ``avg_retweets`` and
    ``avg_favorites`` are the keys the frame is subscripted with, not the
    ``retweet_count`` and ``favorite_count`` columns ``AVG()`` reduces.
    """
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert alias in _emitted_query(mock_run_query_returning_tweet_rows)


def test_get_tweet_analytics_targets_the_configured_dataset(
    mock_run_query_returning_tweet_rows,
):
    """The emitted SQL names the dataset from ``settings.BIGQUERY_DATASET``."""
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _emitted_query(mock_run_query_returning_tweet_rows)

    assert analytics_service.settings.BIGQUERY_DATASET in query
    assert "{dataset}.tweets".format(
        dataset=analytics_service.settings.BIGQUERY_DATASET
    ) in query


# --------------------------------------------------------------------------- #
# get_user_analytics -- happy path and the legacy key-name divergence.
# --------------------------------------------------------------------------- #


def test_get_user_analytics_totals_the_active_user_counts(
    mock_run_query_returning_user_rows,
):
    """``total_active_users`` is the sum of the rows' ``active_users``.

    The two rows carry 3 and 5, so the sum is 8 and the mean is 4.0.
    """
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["total_active_users"] == EXPECTED_TOTAL


def test_get_user_analytics_averages_the_daily_active_user_counts(
    mock_run_query_returning_user_rows,
):
    """``avg_daily_active_users`` is the mean of the rows' ``active_users``."""
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_daily_active_users"] == EXPECTED_DAILY_MEAN


def test_get_user_analytics_averages_the_follower_averages(
    mock_run_query_returning_user_rows,
):
    """``avg_followers`` is the mean of the rows' ``avg_followers``."""
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_followers"] == EXPECTED_FIRST_AVERAGE


def test_get_user_analytics_averages_the_friend_averages(
    mock_run_query_returning_user_rows,
):
    """``avg_friends`` is the mean of the rows' ``avg_friends``."""
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_friends"] == EXPECTED_SECOND_AVERAGE


def test_get_user_analytics_returns_the_declared_key_set(
    mock_run_query_returning_user_rows,
):
    """The result carries exactly its five declared keys."""
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert set(result) == set(USER_ANALYTICS_KEYS)


def test_get_user_analytics_omits_the_legacy_total_users_key(
    mock_run_query_returning_user_rows,
):
    """The result carries ``total_active_users`` and not ``total_users``.

    Legacy ``tests/test_api.py::test_get_user_analytics`` asserted
    ``total_users`` in the body of ``GET /analytics/users``.  That route is not
    implemented, and the key the implementing function returns is
    ``total_active_users``, so the legacy expectation was wrong independently
    of the missing route.
    """
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert LEGACY_USER_TOTAL_KEY not in result
    assert "total_active_users" in result


def test_get_user_analytics_coerces_the_metric_types(
    mock_run_query_returning_user_rows,
):
    """The total is an ``int`` and the three averages are ``float``."""
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert type(result["total_active_users"]) is int
    assert type(result["avg_daily_active_users"]) is float
    assert type(result["avg_followers"]) is float
    assert type(result["avg_friends"]) is float


def test_get_user_analytics_daily_breakdown_is_records_shaped(
    mock_run_query_returning_user_rows,
):
    """``daily_breakdown`` is a list of plain dicts equal to the rows."""
    expected_rows = _user_rows()

    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )
    breakdown = result["daily_breakdown"]

    assert type(breakdown) is list
    assert len(breakdown) == EXPECTED_BREAKDOWN_LENGTH
    assert all(type(record) is dict for record in breakdown)
    assert breakdown == expected_rows


def test_get_user_analytics_runs_exactly_one_query(
    mock_run_query_returning_user_rows,
):
    """One query is issued, as a single positional argument."""
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    _emitted_query(mock_run_query_returning_user_rows)


def test_get_user_analytics_emits_the_requested_date_range(
    mock_run_query_returning_user_rows,
):
    """The emitted SQL carries the caller's dates in a ``BETWEEN`` clause."""
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _emitted_query(mock_run_query_returning_user_rows)

    assert (
        "BETWEEN '{start}' AND '{end}'".format(
            start=FIRST_ANALYTICS_DATE, end=SECOND_ANALYTICS_DATE
        )
        in query
    )


@pytest.mark.parametrize("alias", USER_QUERY_ALIASES)
def test_get_user_analytics_emits_the_selected_alias(
    alias, mock_run_query_returning_user_rows
):
    """Each ``as`` alias the subject indexes appears in the emitted SQL."""
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert alias in _emitted_query(mock_run_query_returning_user_rows)


def test_get_user_analytics_targets_the_configured_dataset(
    mock_run_query_returning_user_rows,
):
    """The emitted SQL names the dataset from ``settings.BIGQUERY_DATASET``.

    Both aggregations read the same ``tweets`` table; the user query derives
    its counts from the ``user_id``, ``followers_count`` and
    ``friends_count`` columns of that table rather than from a separate users
    table.
    """
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _emitted_query(mock_run_query_returning_user_rows)

    assert analytics_service.settings.BIGQUERY_DATASET in query
    assert "{dataset}.tweets".format(
        dataset=analytics_service.settings.BIGQUERY_DATASET
    ) in query


# --------------------------------------------------------------------------- #
# Edge case: an empty result set.  Produced by returning no rows at all, never
# by removing a key from a row.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("aggregation_name", "missing_column"),
    (
        pytest.param("get_tweet_analytics", "tweet_count", id="tweet"),
        pytest.param("get_user_analytics", "active_users", id="user"),
    ),
)
def test_aggregation_raises_key_error_on_empty_result(
    aggregation_name, missing_column, mock_run_query
):
    """An empty result set raises ``KeyError`` naming the first column read.

    ``DataFrame([])`` carries no columns, so the first subscript in the metric
    dictionary fails: ``'tweet_count'`` for ``get_tweet_analytics`` and
    ``'active_users'`` for ``get_user_analytics``.  Neither function returns a
    zeroed result, and the query is still issued before the failure.
    """
    mock_run_query.return_value = []
    aggregation = getattr(analytics_service, aggregation_name)

    with pytest.raises(KeyError) as excinfo:
        aggregation(FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE)

    assert excinfo.value.args[0] == missing_column
    assert mock_run_query.call_count == 1


# --------------------------------------------------------------------------- #
# Error disposition: propagation.  The subject contains no try and no except.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("aggregation_name", PUBLIC_AGGREGATIONS)
def test_aggregation_propagates_query_failure(
    aggregation_name, mock_run_query
):
    """A failure raised by ``run_query`` leaves the aggregation unchanged.

    The subject wraps nothing in ``try``, so the exception type and message a
    caller sees are the ones ``run_query`` raised.  ``update_tweet`` in
    ``app/db/firestore.py`` takes the opposite disposition and returns
    ``False`` on a swallowed failure.
    """
    mock_run_query.side_effect = RuntimeError(QUERY_FAILURE_MESSAGE)
    aggregation = getattr(analytics_service, aggregation_name)

    with pytest.raises(RuntimeError, match=QUERY_FAILURE_MESSAGE) as excinfo:
        aggregation(FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE)

    assert type(excinfo.value) is RuntimeError
    assert excinfo.value.args == (QUERY_FAILURE_MESSAGE,)


# --------------------------------------------------------------------------- #
# Divergence: the date range is interpolated without validation.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("start_date", "end_date"), UNVALIDATED_DATE_RANGES)
def test_get_tweet_analytics_interpolates_an_unvalidated_date_range(
    start_date, end_date, mock_run_query_returning_tweet_rows
):
    """A range the subject never validates reaches the SQL text verbatim.

    Both an inverted range, whose end precedes its start, and a string that is
    not a date are accepted: the call returns its ordinary aggregate and the
    ``BETWEEN`` clause carries the two arguments exactly as they were passed.
    """
    result = analytics_service.get_tweet_analytics(start_date, end_date)

    query = _emitted_query(mock_run_query_returning_tweet_rows)

    assert (
        "BETWEEN '{start}' AND '{end}'".format(start=start_date, end=end_date)
        in query
    )
    assert result["total_tweets"] == EXPECTED_TOTAL


@pytest.mark.parametrize(("start_date", "end_date"), UNVALIDATED_DATE_RANGES)
def test_get_user_analytics_interpolates_an_unvalidated_date_range(
    start_date, end_date, mock_run_query_returning_user_rows
):
    """A range the subject never validates reaches the SQL text verbatim."""
    result = analytics_service.get_user_analytics(start_date, end_date)

    query = _emitted_query(mock_run_query_returning_user_rows)

    assert (
        "BETWEEN '{start}' AND '{end}'".format(start=start_date, end=end_date)
        in query
    )
    assert result["total_active_users"] == EXPECTED_TOTAL

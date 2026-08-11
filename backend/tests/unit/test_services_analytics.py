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


RUN_QUERY_TARGET = "app.services.analytics_service.run_query"
PUBLIC_AGGREGATIONS = ("get_tweet_analytics", "get_user_analytics")
ABSENT_LEGACY_NAMES = ("AnalyticsService", "calculate_engagement_rate")
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


SECOND_ROW_COUNT = 5
SECOND_ROW_FIRST_AVERAGE = 2.0
SECOND_ROW_SECOND_AVERAGE = 4.0
EXPECTED_TOTAL = 8
EXPECTED_DAILY_MEAN = 4.0
EXPECTED_FIRST_AVERAGE = 1.5
EXPECTED_SECOND_AVERAGE = 3.0
EXPECTED_BREAKDOWN_LENGTH = 2
TWEET_QUERY_ALIASES = (
    "as date",
    "as tweet_count",
    "as avg_retweets",
    "as avg_favorites",
)
USER_QUERY_ALIASES = (
    "as date",
    "as active_users",
    "as avg_followers",
    "as avg_friends",
)
QUERY_FAILURE_MESSAGE = "query failed"
INVERTED_START_DATE = "2024-12-31"
INJECTION_START_DATE = "{date}' OR 1=1 --".format(date=FIRST_ANALYTICS_DATE)

UNVALIDATED_DATE_RANGES = (
    pytest.param(INVERTED_START_DATE, FIRST_ANALYTICS_DATE, id="inverted"),
    pytest.param("not-a-date", "also-not-a-date", id="malformed"),
    pytest.param(INJECTION_START_DATE, SECOND_ANALYTICS_DATE, id="injection"),
)


import re
TWEET_SELECT_EXPRESSIONS = (
    "DATE(created_at) as date",
    "COUNT(*) as tweet_count",
    "AVG(retweet_count) as avg_retweets",
    "AVG(favorite_count) as avg_favorites",
)
USER_SELECT_EXPRESSIONS = (
    "DATE(created_at) as date",
    "COUNT(DISTINCT user_id) as active_users",
    "AVG(followers_count) as avg_followers",
    "AVG(friends_count) as avg_friends",
)
SELECT_LIST_SEPARATOR = ", "
FILTERED_EXPRESSION = "DATE(created_at)"
GROUP_BY_CLAUSE = "GROUP BY {0}".format(FILTERED_EXPRESSION)
ORDER_BY_CLAUSE = "ORDER BY date"
TWEET_QUERY_TEMPLATE = (
    "SELECT DATE(created_at) as date, COUNT(*) as tweet_count, "
    "AVG(retweet_count) as avg_retweets, AVG(favorite_count) as avg_favorites "
    "FROM `{dataset}.tweets` "
    "WHERE DATE(created_at) BETWEEN '{start}' AND '{end}' "
    "GROUP BY DATE(created_at) "
    "ORDER BY date"
)
USER_QUERY_TEMPLATE = (
    "SELECT DATE(created_at) as date, "
    "COUNT(DISTINCT user_id) as active_users, "
    "AVG(followers_count) as avg_followers, "
    "AVG(friends_count) as avg_friends "
    "FROM `{dataset}.tweets` "
    "WHERE DATE(created_at) BETWEEN '{start}' AND '{end}' "
    "GROUP BY DATE(created_at) "
    "ORDER BY date"
)


def _tweet_rows():
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
    assert mock_run_query.call_count == 1
    positional, keyword = mock_run_query.call_args
    assert keyword == {}
    assert len(positional) == 1
    return positional[0]


@pytest.fixture
def mock_run_query():
    """Patch app.services.analytics_service.run_query, the name the subject
    bound at import.
    """
    with patch(RUN_QUERY_TARGET) as replacement:
        yield replacement


@pytest.fixture
def mock_run_query_returning_tweet_rows(mock_run_query):
    mock_run_query.return_value = _tweet_rows()
    return mock_run_query


@pytest.fixture
def mock_run_query_returning_user_rows(mock_run_query):
    mock_run_query.return_value = _user_rows()
    return mock_run_query


@pytest.mark.parametrize("name", PUBLIC_AGGREGATIONS)
def test_module_exposes_aggregation(name):
    assert callable(getattr(analytics_service, name))


@pytest.mark.parametrize("name", ABSENT_LEGACY_NAMES)
def test_module_does_not_expose_legacy_name(name):
    assert not hasattr(analytics_service, name)


def test_run_query_is_bound_into_the_subject_module():
    assert analytics_service.run_query is bigquery.run_query


def test_mock_run_query_replaces_the_subject_module_attribute(mock_run_query):
    assert analytics_service.run_query is mock_run_query
    assert bigquery.run_query is not mock_run_query


def test_get_tweet_analytics_totals_the_tweet_counts(
    mock_run_query_returning_tweet_rows,
):
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["total_tweets"] == EXPECTED_TOTAL


def test_get_tweet_analytics_averages_the_daily_tweet_counts(
    mock_run_query_returning_tweet_rows,
):
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_daily_tweets"] == EXPECTED_DAILY_MEAN


def test_get_tweet_analytics_averages_the_retweet_averages(
    mock_run_query_returning_tweet_rows,
):
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_retweets"] == EXPECTED_FIRST_AVERAGE


def test_get_tweet_analytics_averages_the_favorite_averages(
    mock_run_query_returning_tweet_rows,
):
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_favorites"] == EXPECTED_SECOND_AVERAGE


def test_get_tweet_analytics_returns_the_declared_key_set(
    mock_run_query_returning_tweet_rows,
):
    result = analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert set(result) == set(TWEET_ANALYTICS_KEYS)


def test_get_tweet_analytics_coerces_the_metric_types(
    mock_run_query_returning_tweet_rows,
):
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
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    _emitted_query(mock_run_query_returning_tweet_rows)


def test_get_tweet_analytics_emits_the_requested_date_range(
    mock_run_query_returning_tweet_rows,
):
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
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert alias in _emitted_query(mock_run_query_returning_tweet_rows)


def test_get_tweet_analytics_targets_the_configured_dataset(
    mock_run_query_returning_tweet_rows,
):
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _emitted_query(mock_run_query_returning_tweet_rows)

    assert analytics_service.settings.BIGQUERY_DATASET in query
    assert "{dataset}.tweets".format(
        dataset=analytics_service.settings.BIGQUERY_DATASET
    ) in query


def test_get_user_analytics_totals_the_active_user_counts(
    mock_run_query_returning_user_rows,
):
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["total_active_users"] == EXPECTED_TOTAL


def test_get_user_analytics_averages_the_daily_active_user_counts(
    mock_run_query_returning_user_rows,
):
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_daily_active_users"] == EXPECTED_DAILY_MEAN


def test_get_user_analytics_averages_the_follower_averages(
    mock_run_query_returning_user_rows,
):
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_followers"] == EXPECTED_FIRST_AVERAGE


def test_get_user_analytics_averages_the_friend_averages(
    mock_run_query_returning_user_rows,
):
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert result["avg_friends"] == EXPECTED_SECOND_AVERAGE


def test_get_user_analytics_returns_the_declared_key_set(
    mock_run_query_returning_user_rows,
):
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert set(result) == set(USER_ANALYTICS_KEYS)


def test_get_user_analytics_omits_the_legacy_total_users_key(
    mock_run_query_returning_user_rows,
):
    result = analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert LEGACY_USER_TOTAL_KEY not in result
    assert "total_active_users" in result


def test_get_user_analytics_coerces_the_metric_types(
    mock_run_query_returning_user_rows,
):
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
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    _emitted_query(mock_run_query_returning_user_rows)


def test_get_user_analytics_emits_the_requested_date_range(
    mock_run_query_returning_user_rows,
):
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
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert alias in _emitted_query(mock_run_query_returning_user_rows)


def test_get_user_analytics_targets_the_configured_dataset(
    mock_run_query_returning_user_rows,
):
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _emitted_query(mock_run_query_returning_user_rows)

    assert analytics_service.settings.BIGQUERY_DATASET in query
    assert "{dataset}.tweets".format(
        dataset=analytics_service.settings.BIGQUERY_DATASET
    ) in query


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
    mock_run_query.return_value = []
    aggregation = getattr(analytics_service, aggregation_name)

    with pytest.raises(KeyError) as excinfo:
        aggregation(FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE)

    assert excinfo.value.args[0] == missing_column
    assert mock_run_query.call_count == 1


@pytest.mark.parametrize("aggregation_name", PUBLIC_AGGREGATIONS)
def test_aggregation_propagates_query_failure(
    aggregation_name, mock_run_query
):
    mock_run_query.side_effect = RuntimeError(QUERY_FAILURE_MESSAGE)
    aggregation = getattr(analytics_service, aggregation_name)

    with pytest.raises(RuntimeError, match=QUERY_FAILURE_MESSAGE) as excinfo:
        aggregation(FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE)

    assert type(excinfo.value) is RuntimeError
    assert excinfo.value.args == (QUERY_FAILURE_MESSAGE,)


@pytest.mark.parametrize(("start_date", "end_date"), UNVALIDATED_DATE_RANGES)
def test_get_tweet_analytics_interpolates_an_unvalidated_date_range(
    start_date, end_date, mock_run_query_returning_tweet_rows
):
    result = analytics_service.get_tweet_analytics(start_date, end_date)

    query = _emitted_query(mock_run_query_returning_tweet_rows)

    assert start_date in query
    assert end_date in query
    assert (
        "BETWEEN '{start}' AND '{end}'".format(start=start_date, end=end_date)
        in query
    )
    assert result["total_tweets"] == EXPECTED_TOTAL


@pytest.mark.parametrize(("start_date", "end_date"), UNVALIDATED_DATE_RANGES)
def test_get_user_analytics_interpolates_an_unvalidated_date_range(
    start_date, end_date, mock_run_query_returning_user_rows
):
    result = analytics_service.get_user_analytics(start_date, end_date)

    query = _emitted_query(mock_run_query_returning_user_rows)

    assert start_date in query
    assert end_date in query
    assert (
        "BETWEEN '{start}' AND '{end}'".format(start=start_date, end=end_date)
        in query
    )
    assert result["total_active_users"] == EXPECTED_TOTAL


def _normalised_query(mock_run_query):
    """Return the emitted SQL with every whitespace run collapsed to a space.

    The subject builds each statement as a fourteen-line indented f-string, so
    the raw text carries newlines and leading spaces that no consumer depends
    on.  Collapsing them is what lets a clause be asserted as the one-line
    literal it is in SQL terms, and it is the only transformation applied: no
    token is reordered, removed or lower-cased.

    Goes through :func:`_emitted_query`, so the single-positional-argument call
    shape is pinned here too.
    """
    return re.sub(r"\s+", " ", _emitted_query(mock_run_query)).strip()


@pytest.mark.parametrize("expression", TWEET_SELECT_EXPRESSIONS)
def test_get_tweet_analytics_selects_the_expression(
    expression, mock_run_query_returning_tweet_rows
):
    """Each selected expression appears with its own alias attached.

    The pair is what matters: ``avg_retweets`` is the mean of
    ``retweet_count`` and ``avg_favorites`` the mean of ``favorite_count``, so
    swapping the two columns would leave both aliases present and both
    aggregates wrong.
    """
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert expression in _normalised_query(
        mock_run_query_returning_tweet_rows
    )


def test_get_tweet_analytics_selects_exactly_those_four_expressions(
    mock_run_query_returning_tweet_rows,
):
    """The ``SELECT`` list is those four expressions, in order, and no others.

    Read as the text between ``SELECT`` and ``FROM`` and compared for equality,
    so a fifth column, a dropped column or a reordering is reported -- none of
    which a per-expression containment assertion can see.
    """
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_tweet_rows)
    select_list = query.split("SELECT ", 1)[1].split(" FROM ", 1)[0]

    assert select_list == SELECT_LIST_SEPARATOR.join(
        TWEET_SELECT_EXPRESSIONS
    )


def test_get_tweet_analytics_reads_from_the_dataset_tweets_table(
    mock_run_query_returning_tweet_rows,
):
    """The ``FROM`` clause names the backticked ``<dataset>.tweets`` table.

    Asserted as the clause rather than as a bare substring, so the dataset
    appearing anywhere else in the statement would not satisfy it.
    """
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_tweet_rows)

    assert "FROM `{dataset}.tweets` WHERE".format(
        dataset=analytics_service.settings.BIGQUERY_DATASET
    ) in query


def test_get_tweet_analytics_filters_on_the_created_at_date(
    mock_run_query_returning_tweet_rows,
):
    """The ``WHERE`` clause filters ``DATE(created_at)``, not ``created_at``.

    The expression, the two dates and the clause that follows are asserted
    together, which pins what is compared as well as what it is compared to: a
    filter moved onto the raw timestamp, or onto another column, would keep the
    same ``BETWEEN`` values.
    """
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_tweet_rows)

    assert (
        "WHERE {expression} BETWEEN '{start}' AND '{end}' {group_by}".format(
            expression=FILTERED_EXPRESSION,
            start=FIRST_ANALYTICS_DATE,
            end=SECOND_ANALYTICS_DATE,
            group_by=GROUP_BY_CLAUSE,
        )
        in query
    )


def test_get_tweet_analytics_groups_by_the_created_at_date(
    mock_run_query_returning_tweet_rows,
):
    """The statement groups on ``DATE(created_at)``, one row per day.

    Grouping is what makes ``daily_breakdown`` daily and what makes
    ``avg_daily_tweets`` a mean over days; dropping it would collapse the
    result to a single row and change every metric the function returns.
    """
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_tweet_rows)

    assert "{group_by} {order_by}".format(
        group_by=GROUP_BY_CLAUSE, order_by=ORDER_BY_CLAUSE
    ) in query


def test_get_tweet_analytics_orders_by_the_date_alias(
    mock_run_query_returning_tweet_rows,
):
    """The statement ends by ordering on the ``date`` alias.

    Asserted as the end of the text, so nothing follows the ordering -- no
    ``LIMIT``, no second clause -- and the order is ascending by omission.
    """
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_tweet_rows)

    assert query.endswith(ORDER_BY_CLAUSE)


def test_get_tweet_analytics_emits_the_expected_statement(
    mock_run_query_returning_tweet_rows,
):
    """The whole normalised statement equals the specified text.

    The exhaustive form of the cases above: every token of the statement is
    pinned at once, with only the dataset and the caller's two dates supplied.
    The clause-level cases are kept because this one reports a single diff
    wherever the change is, while they name the clause that moved.
    """
    analytics_service.get_tweet_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_tweet_rows)

    assert query == TWEET_QUERY_TEMPLATE.format(
        dataset=analytics_service.settings.BIGQUERY_DATASET,
        start=FIRST_ANALYTICS_DATE,
        end=SECOND_ANALYTICS_DATE,
    )


@pytest.mark.parametrize("expression", USER_SELECT_EXPRESSIONS)
def test_get_user_analytics_selects_the_expression(
    expression, mock_run_query_returning_user_rows
):
    """Each selected expression appears with its own alias attached.

    ``COUNT(DISTINCT user_id) as active_users`` is the case that matters most:
    dropping ``DISTINCT``, or counting rows instead, would leave the alias --
    and therefore ``total_active_users`` and ``avg_daily_active_users`` --
    intact while making both a tweet count.
    """
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    assert expression in _normalised_query(mock_run_query_returning_user_rows)


def test_get_user_analytics_selects_exactly_those_four_expressions(
    mock_run_query_returning_user_rows,
):
    """The ``SELECT`` list is those four expressions, in order, and no more."""
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_user_rows)
    select_list = query.split("SELECT ", 1)[1].split(" FROM ", 1)[0]

    assert select_list == SELECT_LIST_SEPARATOR.join(USER_SELECT_EXPRESSIONS)


def test_get_user_analytics_reads_from_the_dataset_tweets_table(
    mock_run_query_returning_user_rows,
):
    """The ``FROM`` clause names the same ``<dataset>.tweets`` table.

    There is no separate users table: the user metrics are derived from the
    ``user_id``, ``followers_count`` and ``friends_count`` columns of the
    tweets table, which is why ``active_users`` needs ``DISTINCT``.
    """
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_user_rows)

    assert "FROM `{dataset}.tweets` WHERE".format(
        dataset=analytics_service.settings.BIGQUERY_DATASET
    ) in query


def test_get_user_analytics_filters_on_the_created_at_date(
    mock_run_query_returning_user_rows,
):
    """The ``WHERE`` clause filters ``DATE(created_at)``, not the timestamp.

    The same clause the tweet statement uses, asserted here so neither
    aggregation can drift onto the raw ``created_at`` on its own.
    """
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_user_rows)

    assert (
        "WHERE {expression} BETWEEN '{start}' AND '{end}' {group_by}".format(
            expression=FILTERED_EXPRESSION,
            start=FIRST_ANALYTICS_DATE,
            end=SECOND_ANALYTICS_DATE,
            group_by=GROUP_BY_CLAUSE,
        )
        in query
    )


def test_get_user_analytics_groups_by_the_created_at_date(
    mock_run_query_returning_user_rows,
):
    """The statement groups on ``DATE(created_at)``, one row per day.

    ``avg_daily_active_users`` is a mean over those groups, so the grouping key
    is part of what that metric means.
    """
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_user_rows)

    assert "{group_by} {order_by}".format(
        group_by=GROUP_BY_CLAUSE, order_by=ORDER_BY_CLAUSE
    ) in query


def test_get_user_analytics_orders_by_the_date_alias(
    mock_run_query_returning_user_rows,
):
    """The statement ends by ordering on the ``date`` alias."""
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_user_rows)

    assert query.endswith(ORDER_BY_CLAUSE)


def test_get_user_analytics_emits_the_expected_statement(
    mock_run_query_returning_user_rows,
):
    """The whole normalised statement equals the specified text."""
    analytics_service.get_user_analytics(
        FIRST_ANALYTICS_DATE, SECOND_ANALYTICS_DATE
    )

    query = _normalised_query(mock_run_query_returning_user_rows)

    assert query == USER_QUERY_TEMPLATE.format(
        dataset=analytics_service.settings.BIGQUERY_DATASET,
        start=FIRST_ANALYTICS_DATE,
        end=SECOND_ANALYTICS_DATE,
    )

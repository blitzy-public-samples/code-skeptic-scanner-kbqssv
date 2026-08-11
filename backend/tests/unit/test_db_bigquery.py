"""Unit suite for ``app/db/bigquery.py``: the BigQuery data-access wrappers.

``app/db/bigquery.py`` binds ``google.cloud.bigquery.Client`` and
``app.core.config.Settings`` into its own namespace, constructs a client at
module scope as ``bq_client``, and exposes three functions: ``get_bq_client``,
``run_query`` and ``insert_tweet_analytics``.

This suite has two halves.

Both reads of the project are **class** attribute reads
    ``get_bq_client`` reads ``Settings.GOOGLE_CLOUD_PROJECT`` off the
    class, and the ``table_id`` f-string in ``insert_tweet_analytics``
    reads it off the class a second time.  pydantic v1 moves declared
    fields out of the class namespace into ``Settings.__fields__``, so
    every one of the three functions raises ``AttributeError`` as
    shipped.  The first half of this module asserts that, unmodified,
    with no fixture applied.
    The two reads are independent: the second happens after ``get_bq_client``
    has already returned, so replacing ``get_bq_client`` alone leaves
    ``insert_tweet_analytics`` raising.
    :func:`test_insert_tweet_analytics_raises_when_only_get_bq_client_is_patched`
    asserts that directly.
The second half asserts the behaviour underneath
    The ``bigquery_settings`` fixture from ``backend/tests/conftest.py``
    substitutes a project-carrying stand-in for the ``Settings`` name bound
    into ``app.db.bigquery``; all three functions are reachable while it holds.
    ``app.db.bigquery.Client`` is patched alongside it, so no real client is
    ever constructed.

What this module asserts
------------------------
Current behaviour as shipped
    ``get_bq_client``, ``run_query`` and ``insert_tweet_analytics`` each raise
    ``AttributeError`` naming ``GOOGLE_CLOUD_PROJECT``; and
    ``insert_tweet_analytics`` still raises when only ``get_bq_client`` is
    replaced.
Client construction
    ``get_bq_client`` returns what ``Client`` produced and passes the project
    as the ``project`` keyword.  ``bq_client`` is built at import time and
    needs neither credentials nor network.
Query results
    ``run_query`` converts each result row through ``dict`` and returns the
    conversions in order, returns ``[]`` for an empty result set, and hands the
    query text to ``client.query`` unchanged.
Insert return discipline
    ``insert_tweet_analytics`` returns ``True`` when ``insert_rows_json``
    reports no errors and ``False`` when it reports any, and it addresses
    ``<project>.tweet_analytics.tweets`` with the payload wrapped in a
    single-element list.
Error disposition
    The module holds no ``try``/``except`` at all, so a failure raised at any
    link reaches the caller as the instance that was raised: the ``Client``
    constructor, ``client.query``, ``query_job.result`` and
    ``insert_rows_json`` alike.  Each link is asserted separately, because each
    is a distinct boundary and a clause added at one of them would leave the
    others' assertions green.  ``update_tweet`` in ``app/db/firestore.py``
    swallows the equivalent failure and returns ``False``; each module's
    disposition is asserted as it is, in its own suite.
Diagnostics
    The only diagnostic this module emits is a ``print`` on the
    errors-returned path.  It is asserted on standard output, and the success
    and propagation paths are asserted to emit nothing.

Isolation
---------
Every assertion below rests on a value this module or the shared fixtures
established, never on ambient state:

* The three ``AttributeError`` cases request no fixture that touches
  ``Settings``, so they run against the module exactly as imported.
* Every unlocked case reaches production through
  ``mock_bigquery_client_class``, which layers ``bigquery_settings`` over a
  patched ``Client``.  Both patches are context-managed and released per
  test, so neither half of the suite can influence the other and no
  execution order matters.
* The substituted project is asserted to be
  :data:`STAND_IN_PROJECT` by
  :func:`test_bigquery_settings_substitutes_the_expected_project`, so the
  literals below stay tied to the fixture that supplies them.
* Rows are mapping-like objects and not mocks: ``dict`` of a
  :class:`unittest.mock.MagicMock` is ``{}``.

Shared setup — the environment normalisation, the Google credential
neutraliser and the network guard — comes from ``backend/tests/conftest.py``.
No real client, credential, socket or clock is used.

.. seealso::

   ``docs/testing/DECISION-LOG.md`` rows D150 (the ``Settings`` stand-in that
   makes the second half reachable), D149 (the patch boundary), D25-D27 and
   D105 (the credential neutraliser and egress guard) and D53 (production
   defects are pinned, not repaired).
   ``docs/testing/TRACEABILITY-MATRIX.md`` records the construct each test
   covers.
"""
import pytest
from unittest.mock import MagicMock, patch
import app.db.bigquery as bigquery
from tests.factories import make_analytics_row
pytestmark = pytest.mark.unit


MISSING_FIELD_NAME = "GOOGLE_CLOUD_PROJECT"
STAND_IN_PROJECT = "test-project"
EXPECTED_TABLE_ID = "test-project.tweet_analytics.tweets"
DIAGNOSTIC_PREFIX = "Errors occurred while inserting rows:"
QUERY_ROW_MAPPINGS = ({"a": 1}, {"a": 2})
EXPECTED_QUERY_RESULT = [{"a": 1}, {"a": 2}]
SAMPLE_QUERY = "SELECT a FROM `test-project.tweet_analytics.tweets`"
NON_EMPTY_ERROR_PAYLOADS = (
    [{"index": 0, "errors": [{"reason": "invalid", "message": "bad row"}]}],
    [{"index": 0}],
    ["unstructured failure"],
)
EMPTY_ERROR_PAYLOADS = ([], None)

#: Failure types injected at the module's four unguarded links.  ``Exception``
#: is included: it is the type the bare clause in
#: ``app/db/firestore.py`` names, so a clause of that shape added here would
#: stop the exception these cases expect to arrive.  The narrower types are
#: subclasses of it, and none of them is caught either.
PROPAGATED_FAILURES = (
    pytest.param(Exception, id="exception"),
    pytest.param(RuntimeError, id="runtimeerror"),
    pytest.param(ConnectionError, id="connectionerror"),
)

#: Messages carried by the injected failures, one per link, each distinct, so a
#: propagated exception identifies the link it was raised at as well as its
#: type.
CLIENT_CONSTRUCTION_FAILURE_MESSAGE = "credentials could not be resolved"
QUERY_SUBMISSION_FAILURE_MESSAGE = "the query was rejected"
RESULT_RESOLUTION_FAILURE_MESSAGE = "the job did not complete"
INSERT_FAILURE_MESSAGE = "the streaming insert failed"

#: Initial value of a variable a completed call would overwrite.  A propagation
#: case finding it still in place has established that the function produced no
#: value at all -- neither a row list, nor ``True``, nor ``False``.
UNREACHED = object()


from types import SimpleNamespace

ALTERNATIVE_PROJECT = "another-test-project"

ALTERNATIVE_TABLE_ID = "another-test-project.tweet_analytics.tweets"

TABLE_ID_SUFFIX = ".tweet_analytics.tweets"

QUERY_FAILURES = (
    pytest.param(RuntimeError, "job submission refused", id="runtimeerror"),
    pytest.param(ValueError, "malformed query text", id="valueerror"),
    pytest.param(Exception, "boom", id="exception"),
)


class _MappingRow:

    def __init__(self, mapping):
        self._mapping = dict(mapping)
        self.conversions = 0

    def keys(self):
        self.conversions += 1
        return self._mapping.keys()

    def __getitem__(self, key):
        return self._mapping[key]

    def __repr__(self):
        return "_MappingRow({0!r})".format(self._mapping)


@pytest.fixture
def mock_bigquery_client_class(bigquery_settings):
    """Patch the subject-bound Client while bigquery_settings supplies the
    class attribute production reads.
    """
    with patch.object(bigquery, "Client") as client_class:
        client_class.return_value = MagicMock(name="bigquery_client")
        yield client_class


@pytest.fixture
def mock_bigquery_client(mock_bigquery_client_class):
    return mock_bigquery_client_class.return_value


class _ConversionRecordingRow(_MappingRow):
    """A row that counts the ``dict(row)`` conversions applied to it.

    ``run_query`` converts each row through ``dict``, which resolves a
    mapping-like object through ``keys``.  :attr:`conversions` therefore counts
    the conversions the subject performed, which is what a propagation case
    asserts stayed at zero.
    """

    def __init__(self, mapping):
        super().__init__(mapping)
        self.conversions = 0

    def keys(self):
        """Return the column names, recording that a conversion happened."""
        self.conversions += 1
        return super().keys()


@pytest.fixture
def mock_query_result(mock_bigquery_client):
    rows = [_MappingRow(mapping) for mapping in QUERY_ROW_MAPPINGS]
    mock_bigquery_client.query.return_value.result.return_value = rows
    return rows


def test_get_bq_client_raises_attribute_error():
    with pytest.raises(AttributeError, match=MISSING_FIELD_NAME):
        bigquery.get_bq_client()


def test_run_query_raises_attribute_error():
    with pytest.raises(AttributeError, match=MISSING_FIELD_NAME):
        bigquery.run_query(SAMPLE_QUERY)


def test_insert_tweet_analytics_raises_attribute_error():
    with pytest.raises(AttributeError, match=MISSING_FIELD_NAME):
        bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))


def test_attribute_error_names_the_settings_class_and_the_field():
    with pytest.raises(AttributeError) as excinfo:
        bigquery.get_bq_client()

    message = str(excinfo.value)
    assert MISSING_FIELD_NAME in message
    assert "Settings" in message


def test_insert_tweet_analytics_raises_when_only_get_bq_client_is_patched():
    client = MagicMock(name="bigquery_client")

    with patch.object(
        bigquery, "get_bq_client", return_value=client
    ) as patched_get_bq_client:
        with pytest.raises(AttributeError, match=MISSING_FIELD_NAME):
            bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    patched_get_bq_client.assert_called_once_with()
    client.insert_rows_json.assert_not_called()


def test_module_level_client_is_constructed_at_import():
    assert hasattr(bigquery, "bq_client")
    assert bigquery.bq_client is not None


def test_bigquery_settings_substitutes_the_expected_project(bigquery_settings):
    assert bigquery_settings.GOOGLE_CLOUD_PROJECT == STAND_IN_PROJECT


def test_get_bq_client_passes_the_project_keyword(mock_bigquery_client_class):
    bigquery.get_bq_client()

    mock_bigquery_client_class.assert_called_once_with(
        project=STAND_IN_PROJECT
    )


def test_get_bq_client_returns_the_constructed_client(
    mock_bigquery_client_class, mock_bigquery_client
):
    assert bigquery.get_bq_client() is mock_bigquery_client
    assert mock_bigquery_client_class.call_count == 1


def test_run_query_returns_one_dict_per_row(
    mock_bigquery_client, mock_query_result
):
    result = bigquery.run_query(SAMPLE_QUERY)

    assert result == EXPECTED_QUERY_RESULT
    assert len(result) == len(mock_query_result)
    assert all(isinstance(row, dict) for row in result)


def test_run_query_passes_the_query_text_unchanged(
    mock_bigquery_client, mock_query_result
):
    bigquery.run_query(SAMPLE_QUERY)

    mock_bigquery_client.query.assert_called_once_with(SAMPLE_QUERY)


def test_run_query_resolves_the_job_before_reading_rows(
    mock_bigquery_client, mock_query_result
):
    bigquery.run_query(SAMPLE_QUERY)

    mock_bigquery_client.query.return_value.result.assert_called_once_with()


def test_run_query_returns_empty_list_for_no_rows(mock_bigquery_client):
    mock_bigquery_client.query.return_value.result.return_value = []

    assert bigquery.run_query(SAMPLE_QUERY) == []


@pytest.mark.parametrize(
    "errors",
    EMPTY_ERROR_PAYLOADS,
    ids=["empty-list", "none"],
)
def test_insert_tweet_analytics_returns_true_without_errors(
    mock_bigquery_client, errors
):
    mock_bigquery_client.insert_rows_json.return_value = errors

    result = bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    assert result is True


def test_insert_tweet_analytics_prints_nothing_without_errors(
    mock_bigquery_client, capsys
):
    mock_bigquery_client.insert_rows_json.return_value = []

    bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.mark.parametrize(
    "errors",
    NON_EMPTY_ERROR_PAYLOADS,
    ids=["structured", "index-only", "unstructured"],
)
def test_insert_tweet_analytics_returns_false_with_errors(
    mock_bigquery_client, errors
):
    mock_bigquery_client.insert_rows_json.return_value = errors

    result = bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    assert result is False


def test_insert_tweet_analytics_prints_the_returned_errors(
    mock_bigquery_client, capsys
):
    errors = NON_EMPTY_ERROR_PAYLOADS[0]
    mock_bigquery_client.insert_rows_json.return_value = errors

    bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    captured = capsys.readouterr()
    assert DIAGNOSTIC_PREFIX in captured.out
    assert str(errors) in captured.out


def test_insert_tweet_analytics_propagates_insert_failure(
    mock_bigquery_client,
):
    mock_bigquery_client.insert_rows_json.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))


def test_insert_tweet_analytics_prints_nothing_when_the_insert_raises(
    mock_bigquery_client, capsys
):
    mock_bigquery_client.insert_rows_json.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    captured = capsys.readouterr()
    assert captured.out == ""


def test_insert_tweet_analytics_targets_the_configured_table(
    mock_bigquery_client,
):
    analytics_data = make_analytics_row(kind="tweet")
    mock_bigquery_client.insert_rows_json.return_value = []

    bigquery.insert_tweet_analytics(analytics_data)

    mock_bigquery_client.insert_rows_json.assert_called_once_with(
        EXPECTED_TABLE_ID, [analytics_data]
    )


def test_insert_tweet_analytics_builds_one_client_per_call(
    mock_bigquery_client_class, mock_bigquery_client
):
    mock_bigquery_client.insert_rows_json.return_value = []

    bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))
    bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    assert mock_bigquery_client_class.call_count == 2


# --------------------------------------------------------------------------- #
# Error disposition, link by link.
#
# The module holds no ``try``/``except``, so each of its four external calls --
# the ``Client`` constructor, ``client.query``, ``query_job.result`` and
# ``insert_rows_json`` -- is a boundary at which a failure reaches the caller
# unchanged.  Each case below injects at one link of one function, asserts the
# identity, type and message of what escaped, and asserts that the next link was
# not reached.  Both functions are covered at the constructor they share,
# because they call it independently.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_run_query_propagates_a_client_construction_failure(
    mock_bigquery_client_class, mock_bigquery_client, failure_type
):
    """A failing ``Client`` constructor reaches the caller from ``run_query``.

    ``get_bq_client`` is the first statement, so no query is submitted, and no
    row list -- not even an empty one -- is produced.
    """
    failure = failure_type(CLIENT_CONSTRUCTION_FAILURE_MESSAGE)
    mock_bigquery_client_class.side_effect = failure
    returned = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        returned = bigquery.run_query(SAMPLE_QUERY)

    assert excinfo.value is failure
    assert str(excinfo.value) == CLIENT_CONSTRUCTION_FAILURE_MESSAGE
    assert returned is UNREACHED
    mock_bigquery_client.query.assert_not_called()


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_run_query_propagates_a_query_submission_failure(
    mock_bigquery_client, failure_type
):
    """A failing ``client.query`` reaches the caller unchanged.

    The job is never resolved, so ``result()`` is not called and the
    comprehension that converts rows is never entered.
    """
    failure = failure_type(QUERY_SUBMISSION_FAILURE_MESSAGE)
    mock_bigquery_client.query.side_effect = failure
    returned = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        returned = bigquery.run_query(SAMPLE_QUERY)

    assert excinfo.value is failure
    assert str(excinfo.value) == QUERY_SUBMISSION_FAILURE_MESSAGE
    assert returned is UNREACHED
    mock_bigquery_client.query.assert_called_once_with(SAMPLE_QUERY)
    mock_bigquery_client.query.return_value.result.assert_not_called()


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_run_query_propagates_a_result_resolution_failure(
    mock_bigquery_client, failure_type
):
    """A failing ``query_job.result`` reaches the caller unchanged.

    A row is left ready behind the failing call, and its conversion counter
    staying at zero is what establishes that no partial result was assembled:
    the subject neither returns ``[]`` nor reads rows from anywhere else.
    """
    failure = failure_type(RESULT_RESOLUTION_FAILURE_MESSAGE)
    row = _ConversionRecordingRow(QUERY_ROW_MAPPINGS[0])
    query_job = mock_bigquery_client.query.return_value
    query_job.result.return_value = [row]
    query_job.result.side_effect = failure
    returned = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        returned = bigquery.run_query(SAMPLE_QUERY)

    assert excinfo.value is failure
    assert str(excinfo.value) == RESULT_RESOLUTION_FAILURE_MESSAGE
    assert returned is UNREACHED
    query_job.result.assert_called_once_with()
    assert row.conversions == 0


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_insert_tweet_analytics_propagates_a_client_construction_failure(
    mock_bigquery_client_class, mock_bigquery_client, failure_type
):
    """A failing ``Client`` constructor reaches the caller from the insert.

    ``insert_tweet_analytics`` opens with the same ``get_bq_client()`` call, so
    the failure arrives before the table id is built.  It is not converted into
    the ``False`` the errors-returned path uses, which is the distinction this
    case pins: a caller cannot read ``False`` and conclude the rows were
    rejected.
    """
    failure = failure_type(CLIENT_CONSTRUCTION_FAILURE_MESSAGE)
    mock_bigquery_client_class.side_effect = failure
    returned = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        returned = bigquery.insert_tweet_analytics(
            make_analytics_row(kind="tweet")
        )

    assert excinfo.value is failure
    assert str(excinfo.value) == CLIENT_CONSTRUCTION_FAILURE_MESSAGE
    assert returned is UNREACHED
    mock_bigquery_client.insert_rows_json.assert_not_called()


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_insert_tweet_analytics_propagates_every_insert_failure_type(
    mock_bigquery_client, failure_type
):
    """A failing ``insert_rows_json`` escapes whatever its type.

    :func:`test_insert_tweet_analytics_propagates_insert_failure` pins the
    disposition; this case pins that it does not depend on the exception's
    type, ``Exception`` included, and that the escaping object is the very
    instance the client raised rather than a replacement.
    """
    failure = failure_type(INSERT_FAILURE_MESSAGE)
    mock_bigquery_client.insert_rows_json.side_effect = failure
    returned = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        returned = bigquery.insert_tweet_analytics(
            make_analytics_row(kind="tweet")
        )

    assert excinfo.value is failure
    assert str(excinfo.value) == INSERT_FAILURE_MESSAGE
    assert returned is UNREACHED


def test_both_project_reads_follow_the_substituted_settings(
    mock_bigquery_client_class, mock_bigquery_client
):
    """Both class-attribute reads take the project from the substitution.

    This is the support-layer contract behind :data:`STAND_IN_PROJECT` and
    :data:`EXPECTED_TABLE_ID`: rather than reading the fixture's own value back
    out of the fixture, it installs a *different* project over the top and
    follows that value through the two places production reads it — the
    ``project`` keyword ``get_bq_client`` passes to ``Client``, and the
    ``table_id`` the f-string on line 21 builds.  A project hardcoded in either
    place, or a second read that ignored the substitution, would fail here and
    would satisfy an assertion made against the fixture alone.

    The suffix is asserted separately, so what is pinned is a configured
    project joined to a fixed dataset and table rather than one opaque string.
    """
    assert ALTERNATIVE_PROJECT != STAND_IN_PROJECT
    mock_bigquery_client.insert_rows_json.return_value = []
    replacement = SimpleNamespace(GOOGLE_CLOUD_PROJECT=ALTERNATIVE_PROJECT)

    with patch.object(bigquery, "Settings", replacement):
        bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    mock_bigquery_client_class.assert_called_once_with(
        project=ALTERNATIVE_PROJECT
    )
    table_id = mock_bigquery_client.insert_rows_json.call_args[0][0]
    assert table_id == ALTERNATIVE_TABLE_ID
    assert table_id == ALTERNATIVE_PROJECT + TABLE_ID_SUFFIX


@pytest.mark.parametrize("failure_type, message", QUERY_FAILURES)
def test_run_query_propagates_a_failing_job_submission(
    mock_bigquery_client, failure_type, message
):
    """An exception from ``client.query`` reaches the caller unchanged.

    ``run_query`` holds no handler, so the object the client raised is the one
    the caller catches: identity is asserted, which a same-type replacement or
    a re-wrap would not satisfy.  No empty list is substituted and no ``None``
    is returned.
    """
    failure = failure_type(message)
    mock_bigquery_client.query.side_effect = failure

    with pytest.raises(failure_type) as excinfo:
        bigquery.run_query(SAMPLE_QUERY)

    assert excinfo.value is failure
    assert type(excinfo.value) is failure_type
    assert excinfo.value.args == (message,)


def test_run_query_does_not_resolve_a_job_it_failed_to_submit(
    mock_bigquery_client, mock_query_result
):
    """A failing submission stops before the job is resolved or read.

    The result set is programmed with rows that would convert cleanly, so their
    absence from the outcome is the subject's doing.  ``result`` is never
    called and no row is converted, which is what makes this a statement about
    where execution stopped rather than about what the mock happened to hold.
    """
    mock_bigquery_client.query.side_effect = RuntimeError("submission refused")

    with pytest.raises(RuntimeError):
        bigquery.run_query(SAMPLE_QUERY)

    mock_bigquery_client.query.assert_called_once_with(SAMPLE_QUERY)
    mock_bigquery_client.query.return_value.result.assert_not_called()
    assert [row.conversions for row in mock_query_result] == [0, 0]


@pytest.mark.parametrize("failure_type, message", QUERY_FAILURES)
def test_run_query_propagates_a_failing_job_resolution(
    mock_bigquery_client, failure_type, message
):
    """An exception from ``query_job.result`` reaches the caller unchanged.

    Line 14 is as unguarded as line 13, so a job that fails while resolving is
    an exception rather than an empty result set.  The query itself was sent
    before the failure, which distinguishes this boundary from the one
    :func:`test_run_query_propagates_a_failing_job_submission` covers.
    """
    failure = failure_type(message)
    mock_bigquery_client.query.return_value.result.side_effect = failure

    with pytest.raises(failure_type) as excinfo:
        bigquery.run_query(SAMPLE_QUERY)

    assert excinfo.value is failure
    assert type(excinfo.value) is failure_type
    assert excinfo.value.args == (message,)
    mock_bigquery_client.query.assert_called_once_with(SAMPLE_QUERY)


def test_run_query_converts_no_row_when_the_job_fails_to_resolve(
    mock_bigquery_client, mock_query_result
):
    """A failing resolution stops before the conversion comprehension runs.

    The rows the job was programmed to yield are the same objects the happy
    path converts, and each reports zero conversions here, so line 15 was never
    entered and no partial list was built.
    """
    mock_bigquery_client.query.return_value.result.side_effect = RuntimeError(
        "job failed"
    )

    with pytest.raises(RuntimeError):
        bigquery.run_query(SAMPLE_QUERY)

    mock_bigquery_client.query.return_value.result.assert_called_once_with()
    assert [row.conversions for row in mock_query_result] == [0, 0]

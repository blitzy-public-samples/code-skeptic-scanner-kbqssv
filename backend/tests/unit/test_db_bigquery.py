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
    into ``app.db.bigquery``, which is what makes all three functions
    reachable.  ``app.db.bigquery.Client`` is patched alongside it, so no real
    client is ever constructed.

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
    The module holds no ``try``/``except``, so an exception raised by
    ``insert_rows_json`` propagates to the caller.  ``update_tweet`` in
    ``app/db/firestore.py`` swallows and returns ``False``; each module's
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

Reasoning for every choice in this module: ``docs/testing/DECISION-LOG.md``.
``docs/testing/TRACEABILITY-MATRIX.md`` records the construct each test
covers.
"""

import pytest
from unittest.mock import MagicMock, patch

import app.db.bigquery as bigquery
from tests.factories import make_analytics_row

pytestmark = pytest.mark.unit


# The contract this suite pins.  Every literal below is read from
# ``app/db/bigquery.py`` or from the ``bigquery_settings`` stand-in; none is
# recomputed from production code.

#: The field name both class-attribute reads request, and the name the
#: resulting ``AttributeError`` carries.
MISSING_FIELD_NAME = "GOOGLE_CLOUD_PROJECT"

#: ``GOOGLE_CLOUD_PROJECT`` on the stand-in the ``bigquery_settings`` fixture
#: installs.  :func:`test_bigquery_settings_substitutes_the_expected_project`
#: keeps this tied to the fixture.
STAND_IN_PROJECT = "test-project"

#: The table the ``table_id`` f-string addresses once the stand-in supplies the
#: project: ``f"{Settings.GOOGLE_CLOUD_PROJECT}.tweet_analytics.tweets"``.
EXPECTED_TABLE_ID = "test-project.tweet_analytics.tweets"

#: Stable leading text of the only diagnostic the module emits, written to
#: standard output by ``print`` on the errors-returned path.
DIAGNOSTIC_PREFIX = "Errors occurred while inserting rows:"

#: Column mappings the fake result set carries, in ``SELECT`` order.  Each is
#: wrapped in a :class:`_MappingRow` and is what ``dict(row)`` must reproduce.
QUERY_ROW_MAPPINGS = ({"a": 1}, {"a": 2})

#: What ``run_query`` must return for :data:`QUERY_ROW_MAPPINGS`.
EXPECTED_QUERY_RESULT = [{"a": 1}, {"a": 2}]

#: Query text handed to ``run_query``.  Never executed: ``client.query`` is a
#: mock, so the text is only ever compared.
SAMPLE_QUERY = "SELECT a FROM `test-project.tweet_analytics.tweets`"

#: Shapes ``insert_rows_json`` returns that make the ``if errors:`` gate at
#: line 25 truthy.  The first is the per-row error structure the BigQuery
#: client documents; the rest are minimal truthy sequences.
NON_EMPTY_ERROR_PAYLOADS = (
    [{"index": 0, "errors": [{"reason": "invalid", "message": "bad row"}]}],
    [{"index": 0}],
    ["unstructured failure"],
)

#: Shapes ``insert_rows_json`` returns that leave the gate falsy: the empty
#: list the client returns on success, and ``None``, the other falsy value the
#: gate admits.
EMPTY_ERROR_PAYLOADS = ([], None)


class _MappingRow:
    """A result row that converts through ``dict`` the way a real row does.

    ``google.cloud.bigquery.table.Row`` exposes ``keys`` and ``__getitem__``
    and no ``__iter__``, so ``dict(row)`` resolves it through the mapping
    protocol.  This stand-in exposes the same two members, which is what
    ``run_query``'s ``[dict(row) for row in results]`` consumes.
    """

    def __init__(self, mapping):
        self._mapping = dict(mapping)

    def keys(self):
        """Return the column names, as the mapping protocol requires."""
        return self._mapping.keys()

    def __getitem__(self, key):
        """Return the value of column ``key``."""
        return self._mapping[key]

    def __repr__(self):
        """Return a representation naming the columns, for failure output."""
        return "_MappingRow({0!r})".format(self._mapping)


@pytest.fixture
def mock_bigquery_client_class(bigquery_settings):
    """Yield the ``MagicMock`` replacing ``app.db.bigquery.Client``.

    Requesting this fixture also applies ``bigquery_settings``, so the two
    class-attribute reads resolve and all three functions become reachable.
    ``Client`` is patched on ``app.db.bigquery`` — the module that bound the
    name — so ``get_bq_client`` cannot construct a real client and no
    credential or socket is required.

    Yields the patched class.  Its ``return_value`` is the client instance
    every call to ``get_bq_client`` hands back; ``mock_bigquery_client``
    yields that instance directly.
    """
    with patch.object(bigquery, "Client") as client_class:
        client_class.return_value = MagicMock(name="bigquery_client")
        yield client_class


@pytest.fixture
def mock_bigquery_client(mock_bigquery_client_class):
    """Yield the client instance ``get_bq_client`` returns while patched.

    Configure ``query`` or ``insert_rows_json`` on it to drive ``run_query``
    and ``insert_tweet_analytics``.
    """
    return mock_bigquery_client_class.return_value


@pytest.fixture
def mock_query_result(mock_bigquery_client):
    """Wire ``client.query(...).result()`` to :data:`QUERY_ROW_MAPPINGS`.

    Yields the list of :class:`_MappingRow` the fake result set contains, so a
    test can assert against the rows it was given rather than restating them.
    """
    rows = [_MappingRow(mapping) for mapping in QUERY_ROW_MAPPINGS]
    mock_bigquery_client.query.return_value.result.return_value = rows
    return rows


# --------------------------------------------------------------------------- #
# Current behaviour as shipped.
#
# No test in this section requests ``bigquery_settings`` or any fixture
# built on it: each one runs against ``app.db.bigquery`` exactly as
# imported, which is what makes it a record of the module's unmodified
# behaviour.
# --------------------------------------------------------------------------- #


def test_get_bq_client_raises_attribute_error():
    """``get_bq_client`` raises ``AttributeError`` naming the missing field.

    The call reads ``Settings.GOOGLE_CLOUD_PROJECT`` off the class to build the
    ``project`` argument.  pydantic v1 keeps declared fields in
    ``Settings.__fields__`` rather than in the class namespace, so the read
    fails before ``Client`` is called.
    """
    with pytest.raises(AttributeError, match=MISSING_FIELD_NAME):
        bigquery.get_bq_client()


def test_run_query_raises_attribute_error():
    """``run_query`` raises ``AttributeError`` naming the missing field.

    ``run_query`` delegates to ``get_bq_client`` on its first line, so the
    failure reaches the caller before any query is issued.
    """
    with pytest.raises(AttributeError, match=MISSING_FIELD_NAME):
        bigquery.run_query(SAMPLE_QUERY)


def test_insert_tweet_analytics_raises_attribute_error():
    """``insert_tweet_analytics`` raises ``AttributeError`` naming the field.

    Its first line delegates to ``get_bq_client``, so this call fails at the
    same read as :func:`test_get_bq_client_raises_attribute_error`.
    """
    with pytest.raises(AttributeError, match=MISSING_FIELD_NAME):
        bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))


def test_attribute_error_names_the_settings_class_and_the_field():
    """The raised ``AttributeError`` identifies both the class and the field.

    The message names ``Settings`` and ``GOOGLE_CLOUD_PROJECT``: the object the
    read was attempted on, and the attribute that could not be resolved.
    """
    with pytest.raises(AttributeError) as excinfo:
        bigquery.get_bq_client()

    message = str(excinfo.value)
    assert MISSING_FIELD_NAME in message
    assert "Settings" in message


def test_insert_tweet_analytics_raises_when_only_get_bq_client_is_patched():
    """Replacing ``get_bq_client`` alone leaves ``insert_tweet_analytics``
    raising ``AttributeError``.

    The ``table_id`` f-string reads ``Settings.GOOGLE_CLOUD_PROJECT`` a second
    time, after ``get_bq_client`` has already returned.  The two reads are
    therefore independent, and the client this test supplies is never used:
    ``get_bq_client`` is called, and ``insert_rows_json`` is not reached.
    """
    client = MagicMock(name="bigquery_client")

    with patch.object(
        bigquery, "get_bq_client", return_value=client
    ) as patched_get_bq_client:
        with pytest.raises(AttributeError, match=MISSING_FIELD_NAME):
            bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    patched_get_bq_client.assert_called_once_with()
    client.insert_rows_json.assert_not_called()


def test_module_level_client_is_constructed_at_import():
    """``bq_client`` exists on the module, built while it was imported.

    The assignment at module scope runs during collection, before any fixture,
    and completes without credentials or network.  Nothing in production reads
    the attribute: ``get_bq_client`` builds a new client on every call.
    """
    assert hasattr(bigquery, "bq_client")
    assert bigquery.bq_client is not None


# --------------------------------------------------------------------------- #
# Behaviour under the ``Settings`` stand-in.
#
# Every test below reaches production through ``mock_bigquery_client_class`` or
# a fixture built on it, which applies ``bigquery_settings`` and patches
# ``app.db.bigquery.Client`` together.  Both patches are released when the test
# ends.
# --------------------------------------------------------------------------- #


def test_bigquery_settings_substitutes_the_expected_project(bigquery_settings):
    """The stand-in carries :data:`STAND_IN_PROJECT` as its project.

    This is the precondition behind :data:`EXPECTED_TABLE_ID` and the
    ``project`` keyword asserted below.  Asserting it directly keeps those
    literals tied to the fixture that supplies the value.
    """
    assert bigquery_settings.GOOGLE_CLOUD_PROJECT == STAND_IN_PROJECT


def test_get_bq_client_passes_the_project_keyword(mock_bigquery_client_class):
    """``get_bq_client`` constructs one client, passing ``project``.

    The project comes from the substituted ``Settings``, and it is supplied as
    a keyword argument rather than positionally.
    """
    bigquery.get_bq_client()

    mock_bigquery_client_class.assert_called_once_with(
        project=STAND_IN_PROJECT
    )


def test_get_bq_client_returns_the_constructed_client(
    mock_bigquery_client_class, mock_bigquery_client
):
    """``get_bq_client`` returns whatever ``Client`` produced, unwrapped."""
    assert bigquery.get_bq_client() is mock_bigquery_client
    assert mock_bigquery_client_class.call_count == 1


def test_run_query_returns_one_dict_per_row(
    mock_bigquery_client, mock_query_result
):
    """``run_query`` returns each row converted through ``dict``, in order.

    The rows are mapping-like objects rather than dictionaries, so the returned
    value is the product of production's ``dict(row)`` conversion and not a
    pass-through of the fixture's own containers.
    """
    result = bigquery.run_query(SAMPLE_QUERY)

    assert result == EXPECTED_QUERY_RESULT
    assert len(result) == len(mock_query_result)
    assert all(isinstance(row, dict) for row in result)


def test_run_query_passes_the_query_text_unchanged(
    mock_bigquery_client, mock_query_result
):
    """``run_query`` hands the query to ``client.query`` once, positionally."""
    bigquery.run_query(SAMPLE_QUERY)

    mock_bigquery_client.query.assert_called_once_with(SAMPLE_QUERY)


def test_run_query_resolves_the_job_before_reading_rows(
    mock_bigquery_client, mock_query_result
):
    """``run_query`` calls ``result()`` on the job ``query`` returned."""
    bigquery.run_query(SAMPLE_QUERY)

    mock_bigquery_client.query.return_value.result.assert_called_once_with()


def test_run_query_returns_empty_list_for_no_rows(mock_bigquery_client):
    """``run_query`` returns ``[]`` when the result set carries no rows.

    The comprehension yields nothing and the empty list reaches the caller;
    no exception is raised for an empty result.
    """
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
    """``insert_tweet_analytics`` returns ``True`` for a falsy error report.

    Both values ``insert_rows_json`` can return that leave the ``if errors:``
    gate falsy reach the final ``return True``.
    """
    mock_bigquery_client.insert_rows_json.return_value = errors

    result = bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    assert result is True


def test_insert_tweet_analytics_prints_nothing_without_errors(
    mock_bigquery_client, capsys
):
    """``insert_tweet_analytics`` writes nothing when the insert reports none.

    The success path holds no diagnostic.  The errors-returned counterpart is
    :func:`test_insert_tweet_analytics_prints_the_returned_errors`.
    """
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
    """``insert_tweet_analytics`` returns ``False`` for a truthy error report.

    The value is ``False`` itself and not merely falsy.
    """
    mock_bigquery_client.insert_rows_json.return_value = errors

    result = bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    assert result is False


def test_insert_tweet_analytics_prints_the_returned_errors(
    mock_bigquery_client, capsys
):
    """The errors-returned path writes the errors to standard output.

    The module emits this through ``print`` and holds no logger, so the
    diagnostic appears on captured standard output.  Both the fixed prefix and
    the string form of the interpolated report are present.
    """
    errors = NON_EMPTY_ERROR_PAYLOADS[0]
    mock_bigquery_client.insert_rows_json.return_value = errors

    bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    captured = capsys.readouterr()
    assert DIAGNOSTIC_PREFIX in captured.out
    assert str(errors) in captured.out


def test_insert_tweet_analytics_propagates_insert_failure(
    mock_bigquery_client,
):
    """An exception from ``insert_rows_json`` reaches the caller unchanged.

    The module holds no ``try``/``except``, so the exception is neither
    swallowed nor converted to a ``False`` return.  ``update_tweet`` in
    ``app/db/firestore.py`` does swallow; the two dispositions differ and each
    is asserted as it is.
    """
    mock_bigquery_client.insert_rows_json.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))


def test_insert_tweet_analytics_prints_nothing_when_the_insert_raises(
    mock_bigquery_client, capsys
):
    """A propagating insert failure produces no diagnostic output.

    The ``print`` sits behind the ``if errors:`` gate, which a raised exception
    never reaches, so the only record of the failure is the exception itself.
    """
    mock_bigquery_client.insert_rows_json.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    captured = capsys.readouterr()
    assert captured.out == ""


def test_insert_tweet_analytics_targets_the_configured_table(
    mock_bigquery_client,
):
    """The insert addresses ``<project>.tweet_analytics.tweets`` with the row.

    Both arguments are passed positionally, the payload wrapped in a
    single-element list, and the row reaches the client unchanged.
    """
    analytics_data = make_analytics_row(kind="tweet")
    mock_bigquery_client.insert_rows_json.return_value = []

    bigquery.insert_tweet_analytics(analytics_data)

    mock_bigquery_client.insert_rows_json.assert_called_once_with(
        EXPECTED_TABLE_ID, [analytics_data]
    )


def test_insert_tweet_analytics_builds_one_client_per_call(
    mock_bigquery_client_class, mock_bigquery_client
):
    """Each call constructs its own client rather than reusing ``bq_client``.

    ``insert_tweet_analytics`` opens with ``get_bq_client()``, so the
    module-scope ``bq_client`` is not the object the insert is issued against.
    """
    mock_bigquery_client.insert_rows_json.return_value = []

    bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))
    bigquery.insert_tweet_analytics(make_analytics_row(kind="tweet"))

    assert mock_bigquery_client_class.call_count == 2

"""Unit suite for ``app/db/firestore.py``, the Firestore data-access wrappers.

The subject declares five public names: the module-level ``db = Client()``, the
client factory ``get_db()``, and the three wrappers ``add_tweet(tweet_data)``,
``get_tweet(tweet_id)`` and ``update_tweet(tweet_id, update_data)``.  Every
wrapper opens with ``client = get_db()`` and then drives one
``client.collection('tweets')`` chain.

Isolation
---------
``app.db.firestore.get_db`` is replaced in every test in this module through the
``firestore_client`` fixture in ``backend/tests/conftest.py``, which patches the
attribute on this subject — the boundary the wrappers themselves read.
:func:`test_every_test_requests_the_firestore_client_fixture` is the structural
gate that keeps that true for tests added later.  No test in this module
constructs a client, and none calls ``get_db`` in an unpatched state.

What this suite asserts
-----------------------
* ``add_tweet`` returns the ``id`` of element **1** of the pair that
  ``collection('tweets').add(...)`` reports, as a ``str``; element 0's ``id`` is
  never returned.
* ``add_tweet`` writes to the ``tweets`` collection and hands ``.add`` the
  payload object it was given, unchanged and exactly once — including a
  schema-valid payload from ``backend/tests/factories.py``.
* ``get_tweet`` returns the very object ``doc.to_dict()`` produces when
  ``doc.exists`` is truthy, and looks the document up by the id it was passed.
* ``get_tweet`` returns ``None`` when ``doc.exists`` is falsy, and does not read
  the snapshot.
* ``update_tweet`` returns ``True`` when ``doc_ref.update`` returns, having
  applied the update payload exactly once.
* ``update_tweet`` returns ``False``, and raises nothing, when ``doc_ref.update``
  raises — for a bare ``Exception`` and for a narrower type alike.
* ``add_tweet`` and ``get_tweet`` propagate a failure raised at **any** link of
  the chain they drive — client acquisition, ``collection``, ``add``,
  ``document``, ``get`` and ``to_dict`` — as the very instance that was raised,
  and neither produces a return value on that path.
* A propagating link stops the chain: no later call on it is made.
* Each wrapper acquires its client through exactly one ``get_db`` call.
* The module exposes ``db``, ``get_db``, ``add_tweet``, ``get_tweet`` and
  ``update_tweet``, and ``db`` is a ``google.cloud.firestore.Client`` distinct
  from the client the wrappers obtain.
* ``add_response`` is not defined on the module.
* ``get_tweet`` is not a coroutine function.

Current behaviour captured as divergence
----------------------------------------
A missing document makes ``get_tweet`` return ``None`` rather than raise, so a
caller cannot distinguish "absent" from "present and empty", and no test here
asserts an exception for a missing document.

A failing write makes ``update_tweet`` return ``False``.  The bare
``except Exception`` at line 36 discards the failure **silently**: the subject
emits no diagnostic output, binds no exception name and performs no chaining, so
the ``False`` return is the only observable evidence that anything went wrong.
``insert_tweet_analytics`` in ``app/db/bigquery.py`` propagates the equivalent
failure instead; each disposition is asserted in its own suite.

That clause is the module's **only** ``except``, and it guards one statement.
``add_tweet`` and ``get_tweet`` hold none at all, so every failure they meet
reaches the caller unchanged — including a bare ``Exception``, the very type the
``update_tweet`` clause names.  The suite asserts that link by link rather than
once at the boundary, because the two dispositions are one line apart in the
same module and a clause added to the wrong function would otherwise turn a
propagated failure into a silent ``None``: ``get_tweet`` already returns ``None``
for an absent document, so a swallowed read failure would be indistinguishable
from a miss.  Every propagation case therefore asserts the exception's identity,
its type and its message, and that no later link of the chain was reached.

``add_response`` is imported from this module by
``app/tasks/response_generator.py`` line 1 and defined here by nothing.  The
fail-closed shim in ``backend/tests/conftest.py`` binds that name onto this
module for the lifetime of the ``response_generator_module`` fixture and deletes
it again on teardown, so the absence asserted here is the module's shape at any
other time.

``get_tweet`` is synchronous, which is what makes ``await get_tweet(...)`` at
``app/tasks/response_generator.py`` line 12 a ``TypeError``.  That call is
asserted in the response-generator suite; the fact it rests on is pinned here.

Coverage
--------
Lines 8-10, the body of ``get_db``, are executed by no test in this module:
every test replaces that function.

Scope
-----
Every test calls a wrapper directly against a mock client.  The
``Depends(get_db)`` wiring on the tweets router and the
``app.dependency_overrides`` path belong to ``backend/tests/integration/``.

.. seealso::

   ``docs/testing/DECISION-LOG.md`` rows D149 (the patch boundary), D25-D27 and
   D105 (the credential neutraliser and egress guard behind it), D106 (the
   fail-closed shims), D53 (production defects are pinned, not repaired) and
   D70 (the coverage gate this module is measured against).
   ``docs/testing/TRACEABILITY-MATRIX.md`` section G for the ``get_db`` ceiling.
"""
import inspect
from unittest.mock import MagicMock
import pytest
from google.cloud.firestore import Client
import app.db.firestore as firestore
from tests.factories import make_tweet
pytestmark = pytest.mark.unit


TWEETS_COLLECTION = "tweets"
EXPECTED_DOCUMENT_ID = "doc123"
UNRETURNED_ELEMENT_ID = "write-time-not-a-document-id"
TWEET_ID = "1"
MINIMAL_TWEET_PAYLOAD = {"a": 1}
UPDATE_PAYLOAD = {"x": 2}
UPDATE_FAILURES = (
    pytest.param(Exception, "boom", id="exception"),
    pytest.param(RuntimeError, "transport failure", id="runtimeerror"),
    pytest.param(ValueError, "malformed update", id="valueerror"),
)

#: Failures injected at the unguarded links of ``add_tweet`` and ``get_tweet``.
#: ``Exception`` is first and is the case that matters most: it is the type the
#: bare clause in ``update_tweet`` names, so a clause of that shape added to
#: either of these two functions would stop the exception this parametrisation
#: expects to arrive.  The narrower types are subclasses of it and none is
#: caught either.
PROPAGATED_FAILURES = (
    pytest.param(Exception, id="exception"),
    pytest.param(RuntimeError, id="runtimeerror"),
    pytest.param(ConnectionError, id="connectionerror"),
)

PROPAGATED_FAILURES_WITH_MESSAGE = (
    pytest.param(RuntimeError, "transport failure", id="runtimeerror"),
    pytest.param(ValueError, "malformed document", id="valueerror"),
    pytest.param(Exception, "boom", id="exception"),
)

#: Messages carried by the injected failures, one per link.  Each is distinct,
#: so a propagated exception identifies the link it was raised at rather than
#: merely being of the expected type.
ACQUISITION_FAILURE_MESSAGE = "credentials could not be resolved"
COLLECTION_FAILURE_MESSAGE = "collection lookup failed"
ADD_FAILURE_MESSAGE = "the write was rejected"
DOCUMENT_FAILURE_MESSAGE = "document reference could not be built"
SNAPSHOT_FETCH_FAILURE_MESSAGE = "the snapshot could not be read"
SNAPSHOT_CONVERSION_FAILURE_MESSAGE = "the snapshot could not be converted"

#: Initial value of a variable a completed call would overwrite.  A propagation
#: case finding it still in place has established that the wrapper produced no
#: value at all — neither a document id, nor ``None``, nor ``False``.
UNREACHED = object()

#: Values of ``doc.exists`` that send ``get_tweet`` down the ``else`` branch at
#: lines 25-26.  ``False`` is what a real absent snapshot reports; the rest
#: confirm the branch is decided by truthiness rather than by identity.
FALSY_DOCUMENT_EXISTS = (
    pytest.param(False, id="false"),
    pytest.param(None, id="none"),
    pytest.param(0, id="zero"),
    pytest.param("", id="empty-string"),
)
PUBLIC_SURFACE = ("db", "get_db", "add_tweet", "get_tweet", "update_tweet")
UNPATCHED_WRAPPERS = ("add_tweet", "get_tweet", "update_tweet")
UNDEFINED_IMPORTED_NAMES = ("add_response",)
REQUIRED_ISOLATION_FIXTURE = "firestore_client"

#: Recognize both fixture-marker attributes exposed by supported pytest wrapper
#: shapes.
FIXTURE_MARKER_ATTRIBUTES = (
    "_fixture_function_marker",
    "_pytestfixturefunction",
)


WRITE_CAPABLE_METHODS = ("add", "set", "update", "delete", "create")

GET_TWEET_CALL_LEDGER = (
    "collection",
    "collection().document",
    "collection().document().get",
    "collection().document().get().to_dict",
)


@pytest.fixture
def mock_tweets_collection(firestore_client):
    return firestore_client.collection.return_value


@pytest.fixture
def mock_document_reference():
    reference = MagicMock(name="document_reference")
    reference.id = EXPECTED_DOCUMENT_ID
    return reference


@pytest.fixture
def mock_write_result():
    write_result = MagicMock(name="write_result")
    write_result.id = UNRETURNED_ELEMENT_ID
    return write_result


@pytest.fixture
def mock_add_result(
    mock_tweets_collection, mock_write_result, mock_document_reference
):
    result = (mock_write_result, mock_document_reference)
    mock_tweets_collection.add.return_value = result
    return result


@pytest.fixture
def mock_tweet_document(mock_tweets_collection):
    return mock_tweets_collection.document.return_value


@pytest.fixture
def mock_snapshot(mock_tweet_document):
    """Set exists explicitly; an unset MagicMock is truthy."""
    snapshot = mock_tweet_document.get.return_value
    snapshot.exists = True
    return snapshot


def test_add_tweet_returns_the_generated_document_id(
    firestore_client, mock_add_result
):
    returned = firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    assert isinstance(returned, str)
    assert returned == EXPECTED_DOCUMENT_ID


def test_add_tweet_returns_the_id_of_the_second_element(
    firestore_client, mock_add_result, mock_document_reference
):
    returned = firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    assert returned == mock_document_reference.id
    assert returned != UNRETURNED_ELEMENT_ID


def test_add_tweet_writes_to_the_tweets_collection(
    firestore_client, mock_add_result
):
    firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    firestore_client.collection.assert_called_once_with(TWEETS_COLLECTION)


def test_add_tweet_passes_the_payload_to_add_unchanged(
    mock_tweets_collection, mock_add_result
):
    payload = dict(MINIMAL_TWEET_PAYLOAD)

    firestore.add_tweet(payload)

    mock_tweets_collection.add.assert_called_once_with(payload)
    assert mock_tweets_collection.add.call_args[0][0] is payload


def test_add_tweet_accepts_a_schema_valid_payload(
    mock_tweets_collection, mock_add_result
):
    payload = make_tweet()

    returned = firestore.add_tweet(payload)

    assert returned == EXPECTED_DOCUMENT_ID
    mock_tweets_collection.add.assert_called_once_with(payload)
    assert payload == make_tweet()


def test_add_tweet_does_not_read_the_document_snapshot(
    mock_tweets_collection, mock_add_result
):
    firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    mock_tweets_collection.document.assert_not_called()


def test_get_tweet_returns_the_document_dictionary(mock_snapshot):
    stored = make_tweet()
    mock_snapshot.to_dict.return_value = stored

    returned = firestore.get_tweet(TWEET_ID)

    assert returned is stored
    mock_snapshot.to_dict.assert_called_once_with()


def test_get_tweet_reads_from_the_tweets_collection(
    firestore_client, mock_snapshot
):
    firestore.get_tweet(TWEET_ID)

    firestore_client.collection.assert_called_once_with(TWEETS_COLLECTION)


def test_get_tweet_looks_up_the_requested_document_id(
    mock_tweets_collection, mock_snapshot
):
    firestore.get_tweet(TWEET_ID)

    mock_tweets_collection.document.assert_called_once_with(TWEET_ID)


def test_get_tweet_retrieves_the_snapshot_once(
    mock_tweet_document, mock_snapshot
):
    firestore.get_tweet(TWEET_ID)

    mock_tweet_document.get.assert_called_once_with()


@pytest.mark.parametrize("exists", FALSY_DOCUMENT_EXISTS)
def test_get_tweet_returns_none_when_the_document_is_absent(
    mock_snapshot, exists
):
    mock_snapshot.exists = exists

    returned = firestore.get_tweet(TWEET_ID)

    assert returned is None


def test_get_tweet_does_not_read_an_absent_document(mock_snapshot):
    mock_snapshot.exists = False

    firestore.get_tweet(TWEET_ID)

    mock_snapshot.to_dict.assert_not_called()


def test_get_tweet_returns_a_falsy_dictionary_unchanged(mock_snapshot):
    stored = {}
    mock_snapshot.to_dict.return_value = stored

    returned = firestore.get_tweet(TWEET_ID)

    assert returned is stored
    assert returned is not None


@pytest.mark.parametrize("method_name", WRITE_CAPABLE_METHODS)
def test_get_tweet_does_not_write(
    mock_tweets_collection, mock_tweet_document, mock_snapshot, method_name
):
    firestore.get_tweet(TWEET_ID)

    getattr(mock_tweets_collection, method_name).assert_not_called()
    getattr(mock_tweet_document, method_name).assert_not_called()


def test_update_tweet_returns_true_on_success(mock_tweet_document):
    returned = firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    assert returned is True


def test_update_tweet_applies_the_update_payload(mock_tweet_document):
    payload = dict(UPDATE_PAYLOAD)

    firestore.update_tweet(TWEET_ID, payload)

    mock_tweet_document.update.assert_called_once_with(payload)
    assert mock_tweet_document.update.call_args[0][0] is payload


def test_update_tweet_writes_to_the_tweets_collection(
    firestore_client, mock_tweet_document
):
    firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    firestore_client.collection.assert_called_once_with(TWEETS_COLLECTION)


def test_update_tweet_targets_the_requested_document_id(
    mock_tweets_collection, mock_tweet_document
):
    firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    mock_tweets_collection.document.assert_called_once_with(TWEET_ID)


@pytest.mark.parametrize("failure_type, message", UPDATE_FAILURES)
def test_update_tweet_returns_false_when_the_update_fails(
    mock_tweet_document, failure_type, message
):
    mock_tweet_document.update.side_effect = failure_type(message)

    returned = firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    assert returned is False


def test_update_tweet_attempts_the_write_before_failing(mock_tweet_document):
    mock_tweet_document.update.side_effect = Exception("boom")

    firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    mock_tweet_document.update.assert_called_once_with(UPDATE_PAYLOAD)


def test_update_tweet_does_not_read_the_document(mock_tweet_document):
    firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    mock_tweet_document.get.assert_not_called()


# --------------------------------------------------------------------------- #
# Error disposition of the two unguarded wrappers -- lines 12-17 and 19-26.
#
# ``update_tweet`` holds the module's only ``except``, around one statement.
# These two functions hold none, so each link of the chain they drive is a
# boundary at which a failure reaches the caller unchanged.  Every case below
# injects at one link, asserts the identity, type and message of what escaped,
# and asserts that the next link was not reached.
# --------------------------------------------------------------------------- #


def test_add_tweet_propagates_a_client_acquisition_failure(firestore_client):
    """A failure acquiring the client reaches the caller from ``add_tweet``.

    ``get_db`` resolves credentials and constructs a client, so this is the
    first link that can fail.  Nothing on the client is touched afterwards.
    """
    failure = ConnectionError(ACQUISITION_FAILURE_MESSAGE)
    firestore.get_db.side_effect = failure

    with pytest.raises(ConnectionError) as excinfo:
        firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    assert excinfo.value is failure
    assert str(excinfo.value) == ACQUISITION_FAILURE_MESSAGE
    firestore_client.collection.assert_not_called()


def test_add_tweet_propagates_a_collection_lookup_failure(
    firestore_client, mock_tweets_collection
):
    """A failure resolving the collection reaches the caller unchanged.

    ``.add`` is never reached, so nothing is written on this path.
    """
    failure = RuntimeError(COLLECTION_FAILURE_MESSAGE)
    firestore_client.collection.side_effect = failure

    with pytest.raises(RuntimeError) as excinfo:
        firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    assert excinfo.value is failure
    assert str(excinfo.value) == COLLECTION_FAILURE_MESSAGE
    mock_tweets_collection.add.assert_not_called()


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_add_tweet_propagates_a_write_failure(
    mock_tweets_collection, mock_add_result, failure_type
):
    """A failing ``.add`` reaches the caller, whatever its type.

    ``Exception`` is among the cases, which is what distinguishes this
    disposition from ``update_tweet``'s: the same failure that function
    converts into ``False`` escapes here.  The write was attempted, and the
    document id line 17 would have returned is never produced.
    """
    failure = failure_type(ADD_FAILURE_MESSAGE)
    mock_tweets_collection.add.side_effect = failure
    returned = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        returned = firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    assert excinfo.value is failure
    assert str(excinfo.value) == ADD_FAILURE_MESSAGE
    assert returned is UNREACHED
    mock_tweets_collection.add.assert_called_once_with(MINIMAL_TWEET_PAYLOAD)


def test_get_tweet_propagates_a_client_acquisition_failure(firestore_client):
    """A failure acquiring the client reaches the caller from ``get_tweet``.

    The ``None`` an absent document produces is not what a caller sees here:
    the exception arrives instead, so the two outcomes stay distinguishable.
    """
    failure = ConnectionError(ACQUISITION_FAILURE_MESSAGE)
    firestore.get_db.side_effect = failure

    with pytest.raises(ConnectionError) as excinfo:
        firestore.get_tweet(TWEET_ID)

    assert excinfo.value is failure
    assert str(excinfo.value) == ACQUISITION_FAILURE_MESSAGE
    firestore_client.collection.assert_not_called()


def test_get_tweet_propagates_a_collection_lookup_failure(
    firestore_client, mock_tweets_collection
):
    """A failure resolving the collection reaches the caller unchanged.

    The document reference is never resolved, so no read is issued.
    """
    failure = RuntimeError(COLLECTION_FAILURE_MESSAGE)
    firestore_client.collection.side_effect = failure

    with pytest.raises(RuntimeError) as excinfo:
        firestore.get_tweet(TWEET_ID)

    assert excinfo.value is failure
    assert str(excinfo.value) == COLLECTION_FAILURE_MESSAGE
    mock_tweets_collection.document.assert_not_called()


def test_get_tweet_propagates_a_document_lookup_failure(
    mock_tweets_collection, mock_tweet_document
):
    """A failure building the document reference reaches the caller.

    The snapshot is never fetched, so ``doc.exists`` is never consulted and the
    ``None`` branch cannot be reached.
    """
    failure = ValueError(DOCUMENT_FAILURE_MESSAGE)
    mock_tweets_collection.document.side_effect = failure

    with pytest.raises(ValueError) as excinfo:
        firestore.get_tweet(TWEET_ID)

    assert excinfo.value is failure
    assert str(excinfo.value) == DOCUMENT_FAILURE_MESSAGE
    mock_tweet_document.get.assert_not_called()


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_get_tweet_propagates_a_snapshot_read_failure(
    mock_tweet_document, mock_snapshot, failure_type
):
    """A failing ``doc_ref.get()`` reaches the caller, whatever its type.

    The snapshot's contents are never read, and no value -- ``None`` included
    -- is produced, so a read failure and a missing document remain two
    distinguishable outcomes.
    """
    failure = failure_type(SNAPSHOT_FETCH_FAILURE_MESSAGE)
    mock_tweet_document.get.side_effect = failure
    returned = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        returned = firestore.get_tweet(TWEET_ID)

    assert excinfo.value is failure
    assert str(excinfo.value) == SNAPSHOT_FETCH_FAILURE_MESSAGE
    assert returned is UNREACHED
    mock_snapshot.to_dict.assert_not_called()


@pytest.mark.parametrize("failure_type", PROPAGATED_FAILURES)
def test_get_tweet_propagates_a_snapshot_conversion_failure(
    mock_snapshot, failure_type
):
    """A failing ``doc.to_dict()`` reaches the caller, whatever its type.

    This is the last link, reached only once ``doc.exists`` was truthy, so the
    subject has already committed to the ``return`` branch when the failure
    arrives and still produces no value.
    """
    failure = failure_type(SNAPSHOT_CONVERSION_FAILURE_MESSAGE)
    mock_snapshot.to_dict.side_effect = failure
    returned = UNREACHED

    with pytest.raises(failure_type) as excinfo:
        returned = firestore.get_tweet(TWEET_ID)

    assert excinfo.value is failure
    assert str(excinfo.value) == SNAPSHOT_CONVERSION_FAILURE_MESSAGE
    assert returned is UNREACHED
    mock_snapshot.to_dict.assert_called_once_with()


def test_a_read_failure_is_not_converted_into_the_absent_document_result(
    mock_snapshot,
):
    """A failed read is not reported as ``None``.

    ``get_tweet`` has one falsy return, and it means "no such document".  This
    case drives the same function to failure with ``doc.exists`` truthy and
    asserts an exception rather than that value, which is the assertion a
    swallowing clause added to this function would break.
    """
    mock_snapshot.to_dict.side_effect = Exception(
        SNAPSHOT_CONVERSION_FAILURE_MESSAGE
    )

    with pytest.raises(Exception) as excinfo:
        firestore.get_tweet(TWEET_ID)

    assert excinfo.value.__class__ is Exception
    assert str(excinfo.value) == SNAPSHOT_CONVERSION_FAILURE_MESSAGE


# --------------------------------------------------------------------------- #
# Client acquisition.
# --------------------------------------------------------------------------- #


def test_add_tweet_acquires_its_client_once(firestore_client, mock_add_result):
    firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    assert firestore.get_db.call_count == 1


def test_get_tweet_acquires_its_client_once(firestore_client, mock_snapshot):
    firestore.get_tweet(TWEET_ID)

    assert firestore.get_db.call_count == 1


def test_update_tweet_acquires_its_client_once(
    firestore_client, mock_tweet_document
):
    firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    assert firestore.get_db.call_count == 1


def test_wrappers_drive_the_acquired_client_not_the_module_level_one(
    firestore_client, mock_snapshot
):
    firestore.get_tweet(TWEET_ID)

    assert firestore_client.collection.called
    assert firestore.db is not firestore_client


@pytest.mark.parametrize("name", PUBLIC_SURFACE)
def test_module_exposes_its_public_surface(firestore_client, name):
    assert hasattr(firestore, name)


@pytest.mark.parametrize("name", UNDEFINED_IMPORTED_NAMES)
def test_module_does_not_define_the_names_production_imports_from_it(
    firestore_client, name
):
    assert not hasattr(firestore, name)


def test_module_level_client_is_a_firestore_client(firestore_client):
    assert isinstance(firestore.db, Client)


def test_get_tweet_is_not_a_coroutine_function(firestore_client):
    assert inspect.iscoroutinefunction(firestore.get_tweet) is False


@pytest.mark.parametrize("name", UNPATCHED_WRAPPERS)
def test_module_wrappers_are_synchronous(firestore_client, name):
    assert inspect.iscoroutinefunction(getattr(firestore, name)) is False


def _fixture_parameter_names(target):
    """Return fixture parameter names; inspect.signature unwraps pytest's
    fixture wrapper.
    """
    return tuple(inspect.signature(target).parameters)


def _is_fixture(candidate):
    return any(
        hasattr(candidate, attribute) for attribute in FIXTURE_MARKER_ATTRIBUTES
    )


def _resolves_to_required_fixture(name, namespace, visited):
    """Return whether a fixture dependency chain reaches firestore_client."""
    if name == REQUIRED_ISOLATION_FIXTURE:
        return True
    if name in visited:
        return False
    visited.add(name)

    candidate = namespace.get(name)
    if candidate is None or not _is_fixture(candidate):
        return False

    return any(
        _resolves_to_required_fixture(parameter, namespace, visited)
        for parameter in _fixture_parameter_names(candidate)
    )


def test_every_test_requests_the_firestore_client_fixture(firestore_client):
    """Guard that every wrapper test transitively requests firestore_client,
    preventing live Firestore egress.
    """
    namespace = dict(globals())
    tests = {
        name: value
        for name, value in namespace.items()
        if name.startswith("test_") and inspect.isfunction(value)
    }

    unguarded = sorted(
        name
        for name, function in tests.items()
        if not any(
            _resolves_to_required_fixture(parameter, namespace, set())
            for parameter in _fixture_parameter_names(function)
        )
    )

    assert tests, "no test functions were discovered in this module"
    assert unguarded == [], (
        "these tests do not request {0} directly or transitively, so "
        "app.db.firestore.get_db is unpatched while they run: {1}".format(
            REQUIRED_ISOLATION_FIXTURE, ", ".join(unguarded)
        )
    )


def test_get_tweet_makes_only_the_four_calls_of_the_read_path(
    firestore_client, mock_snapshot
):
    """The client sees exactly the read path's four calls, in order.

    This is the whole-ledger counterpart of
    :func:`test_get_tweet_does_not_write`: rather than naming the methods a
    write would use, it names every call the subject is allowed to make, so a
    write issued through any method at all — including one
    :data:`WRITE_CAPABLE_METHODS` does not list — appears as an extra entry.
    """
    firestore.get_tweet(TWEET_ID)

    ledger = tuple(name for name, _, _ in firestore_client.mock_calls)

    assert ledger == GET_TWEET_CALL_LEDGER


@pytest.mark.parametrize("failure_type, message", PROPAGATED_FAILURES_WITH_MESSAGE)
def test_add_tweet_propagates_a_failing_write(
    mock_tweets_collection, failure_type, message
):
    """A raising ``collection.add`` reaches the caller unchanged.

    ``add_tweet`` holds no ``try``, so the object the client raised is the object
    the caller catches — asserted by identity, which a same-type-and-message
    replacement would not satisfy.  Contrast ``update_tweet``, whose failure is
    swallowed into a ``False``.
    """
    failure = failure_type(message)
    mock_tweets_collection.add.side_effect = failure

    with pytest.raises(failure_type) as excinfo:
        firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    assert excinfo.value is failure
    assert type(excinfo.value) is failure_type
    assert excinfo.value.args == (message,)


def test_add_tweet_stops_at_a_failing_write(
    mock_tweets_collection, mock_document_reference
):
    """The failure ends the call: nothing after ``.add`` is reached.

    Line 17 would subscript the result and read ``.id`` off element 1.  The
    prepared reference records neither, so the exception left the function before
    the return value was built, and no document reference was resolved either.
    """
    mock_tweets_collection.add.side_effect = RuntimeError("transport failure")

    with pytest.raises(RuntimeError):
        firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    mock_tweets_collection.add.assert_called_once_with(MINIMAL_TWEET_PAYLOAD)
    mock_tweets_collection.document.assert_not_called()


@pytest.mark.parametrize("failure_type, message", PROPAGATED_FAILURES_WITH_MESSAGE)
def test_get_tweet_propagates_a_failing_snapshot_retrieval(
    mock_tweet_document, failure_type, message
):
    """A raising ``doc_ref.get`` reaches the caller unchanged.

    Line 22 sits outside every handler, so a retrieval failure is *not* the
    ``None`` an absent document produces: the caller sees the exception the
    client raised, by identity.  This is the difference the ``None`` return of
    :func:`test_get_tweet_returns_none_when_the_document_is_absent` would
    otherwise hide.
    """
    failure = failure_type(message)
    mock_tweet_document.get.side_effect = failure

    with pytest.raises(failure_type) as excinfo:
        firestore.get_tweet(TWEET_ID)

    assert excinfo.value is failure
    assert type(excinfo.value) is failure_type
    assert excinfo.value.args == (message,)


def test_get_tweet_stops_at_a_failing_snapshot_retrieval(
    mock_tweet_document, mock_snapshot
):
    """The failure ends the call before the snapshot is read or written.

    ``exists`` is never consulted and ``to_dict`` is never called, so the
    ``if`` at line 23 is not reached; the document is not written to either.
    """
    mock_tweet_document.get.side_effect = RuntimeError("transport failure")

    with pytest.raises(RuntimeError):
        firestore.get_tweet(TWEET_ID)

    mock_tweet_document.get.assert_called_once_with()
    mock_snapshot.to_dict.assert_not_called()
    mock_tweet_document.update.assert_not_called()


@pytest.mark.parametrize("failure_type, message", PROPAGATED_FAILURES_WITH_MESSAGE)
def test_get_tweet_propagates_a_failing_deserialization(
    mock_snapshot, failure_type, message
):
    """A raising ``doc.to_dict`` reaches the caller unchanged.

    Line 24 is the last statement of the truthy branch and is unguarded, so a
    document that cannot be deserialized is an exception rather than a ``None``
    or an empty mapping.  The snapshot reported ``exists`` truthy, so the branch
    was entered and the failure is the conversion itself.
    """
    failure = failure_type(message)
    mock_snapshot.to_dict.side_effect = failure

    with pytest.raises(failure_type) as excinfo:
        firestore.get_tweet(TWEET_ID)

    assert excinfo.value is failure
    assert type(excinfo.value) is failure_type
    assert excinfo.value.args == (message,)


def test_get_tweet_stops_at_a_failing_deserialization(
    mock_tweet_document, mock_snapshot
):
    """The conversion is attempted once and nothing follows it.

    There is no retry, no fallback to the raw snapshot and no write: the single
    ``to_dict`` call is the whole of the subject's attempt.
    """
    mock_snapshot.to_dict.side_effect = RuntimeError("transport failure")

    with pytest.raises(RuntimeError):
        firestore.get_tweet(TWEET_ID)

    mock_snapshot.to_dict.assert_called_once_with()
    mock_tweet_document.get.assert_called_once_with()
    mock_tweet_document.update.assert_not_called()

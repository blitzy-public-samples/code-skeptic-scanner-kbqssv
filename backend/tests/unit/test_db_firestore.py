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
Unpatched, ``get_db`` resolves ambient Google credentials and constructs a real
client, and a wrapper call then performs a live Cloud Firestore round trip.
:func:`test_every_test_requests_the_firestore_client_fixture` is the structural
gate that keeps that guarantee true for tests added later.  No test in this
module constructs a client, and none calls ``get_db`` in an unpatched state.

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
failure instead.  Both dispositions are asserted in their own suites, exactly as
production behaves.

``add_response`` is imported from this module by
``app/tasks/response_generator.py`` line 1 and defined here by nothing, which is
why ``backend/tests/conftest.py`` stands up a fail-closed shim for it.  That
shim binds the name onto this module only for the lifetime of the
``response_generator_module`` fixture and deletes it again on teardown, so the
absence asserted here is the module's real production shape at any other time.

``get_tweet`` being synchronous is what makes ``await get_tweet(...)`` at
``app/tasks/response_generator.py`` line 12 a ``TypeError``.  That call is
asserted in the response-generator suite; the fact it rests on is pinned here.

Coverage
--------
Lines 8-10, the body of ``get_db``, are executed by no test in this module:
every test replaces that function.  ``docs/testing/DECISION-LOG.md`` records the
decision and the gate this module is measured against.

Scope
-----
Every test calls a wrapper directly against a mock client.  The
``Depends(get_db)`` wiring on the tweets router and the
``app.dependency_overrides`` path belong to ``backend/tests/integration/``.
"""

import inspect
from unittest.mock import MagicMock

import pytest
from google.cloud.firestore import Client

import app.db.firestore as firestore
from tests.factories import make_tweet

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Oracles.  Every expected value below is either read from the subject or
# established by a mock this module configures.
# --------------------------------------------------------------------------- #

#: The single collection name the subject hardcodes, at lines 16, 21 and 32.
TWEETS_COLLECTION = "tweets"

#: ``id`` carried by element 1 of the ``add()`` result — the document reference.
#: ``add_tweet`` returns this, because line 17 reads ``doc_ref[1].id``.
EXPECTED_DOCUMENT_ID = "doc123"

#: ``id`` carried by element 0 of the ``add()`` result — the write timestamp.
#: Distinct from :data:`EXPECTED_DOCUMENT_ID`, so a return that indexed element
#: 0 would be observable rather than merely equal.
UNRETURNED_ELEMENT_ID = "write-time-not-a-document-id"

#: Document id passed to ``get_tweet`` and ``update_tweet``.
TWEET_ID = "1"

#: Payload for the ``add_tweet`` call-shape cases.  The subject passes it to the
#: client without inspecting it.
#: :func:`test_add_tweet_accepts_a_schema_valid_payload` covers the full
#: ten-field payload instead.
MINIMAL_TWEET_PAYLOAD = {"a": 1}

#: Payload for ``update_tweet``.
UPDATE_PAYLOAD = {"x": 2}

#: Failures handed to ``doc_ref.update``.  ``Exception`` is the type the bare
#: ``except`` at line 36 names; ``RuntimeError`` and ``ValueError`` are
#: subclasses, and each is caught by the same clause.
UPDATE_FAILURES = (
    pytest.param(Exception, "boom", id="exception"),
    pytest.param(RuntimeError, "transport failure", id="runtimeerror"),
    pytest.param(ValueError, "malformed update", id="valueerror"),
)

#: Values of ``doc.exists`` that send ``get_tweet`` down the ``else`` branch at
#: lines 25-26.  ``False`` is what a real absent snapshot reports; the rest
#: confirm the branch is decided by truthiness rather than by identity.
FALSY_DOCUMENT_EXISTS = (
    pytest.param(False, id="false"),
    pytest.param(None, id="none"),
    pytest.param(0, id="zero"),
    pytest.param("", id="empty-string"),
)

#: Every name the subject is expected to expose.
PUBLIC_SURFACE = ("db", "get_db", "add_tweet", "get_tweet", "update_tweet")

#: The subject's wrappers, which no fixture here replaces.  ``get_db`` is not
#: among them: it is bound to a stand-in for the duration of every test in this
#: module.
UNPATCHED_WRAPPERS = ("add_tweet", "get_tweet", "update_tweet")

#: Names production imports from this module and this module does not define.
#: ``app/tasks/response_generator.py`` line 1 imports ``add_response``.
UNDEFINED_IMPORTED_NAMES = ("add_response",)

#: The fixture that must be in the closure of every test in this module.
REQUIRED_ISOLATION_FIXTURE = "firestore_client"

#: Attributes ``@pytest.fixture`` leaves on the object it returns.  pytest 8.4
#: returns a ``FixtureFunctionDefinition`` carrying ``_fixture_function_marker``;
#: earlier releases return the function itself carrying
#: ``_pytestfixturefunction``.  Either identifies a fixture.
FIXTURE_MARKER_ATTRIBUTES = (
    "_fixture_function_marker",
    "_pytestfixturefunction",
)


# --------------------------------------------------------------------------- #
# Fixtures.  The client patch comes from backend/tests/conftest.py; the mocks
# below shape the call chains the three wrappers drive against it.
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_tweets_collection(firestore_client):
    """Return the collection mock ``client.collection(...)`` resolves to.

    A ``MagicMock`` returns the same child for every argument, so this is the
    object the subject reaches whichever collection name it asks for; the name
    it actually asked for is asserted separately.
    """
    return firestore_client.collection.return_value


@pytest.fixture
def mock_document_reference():
    """Return element 1 of the ``add()`` result, carrying the id oracle.

    ``id`` is assigned after construction rather than through the constructor,
    so it is unambiguously the string :data:`EXPECTED_DOCUMENT_ID` and not an
    auto-created child mock.
    """
    reference = MagicMock(name="document_reference")
    reference.id = EXPECTED_DOCUMENT_ID
    return reference


@pytest.fixture
def mock_write_result():
    """Return element 0 of the ``add()`` result, the write timestamp.

    It carries an ``id`` too, set to :data:`UNRETURNED_ELEMENT_ID`, so the
    element the subject indexes is decided by the assertion rather than by
    which element happens to have an ``id`` at all.
    """
    write_result = MagicMock(name="write_result")
    write_result.id = UNRETURNED_ELEMENT_ID
    return write_result


@pytest.fixture
def mock_add_result(
    mock_tweets_collection, mock_write_result, mock_document_reference
):
    """Configure ``.add()`` to report the two-element pair and return it.

    ``add_tweet`` line 17 subscripts the result, so the value is a real
    :class:`tuple` of ``(write_result, document_reference)``.  A bare
    ``MagicMock`` also satisfies a subscript, answering with a fresh auto-mock
    whose ``id`` is a mock and not a string.
    """
    result = (mock_write_result, mock_document_reference)
    mock_tweets_collection.add.return_value = result
    return result


@pytest.fixture
def mock_tweet_document(mock_tweets_collection):
    """Return the document mock ``.document(...)`` resolves to."""
    return mock_tweets_collection.document.return_value


@pytest.fixture
def mock_snapshot(mock_tweet_document):
    """Return the snapshot ``doc_ref.get()`` resolves to, marked as present.

    ``exists`` is set to ``True`` explicitly.  Left alone it would be a truthy
    auto-mock, which reaches the same branch without stating that it did.
    """
    snapshot = mock_tweet_document.get.return_value
    snapshot.exists = True
    return snapshot


# --------------------------------------------------------------------------- #
# add_tweet -- lines 12-17.
# --------------------------------------------------------------------------- #


def test_add_tweet_returns_the_generated_document_id(
    firestore_client, mock_add_result
):
    """``add_tweet`` returns the document id, and it is a ``str``.

    Both the type and the value are asserted.  Subscripting anything other than
    a genuine two-element sequence yields an auto-created mock whose ``id`` is
    itself a mock, which the type assertion reports and an equality assertion
    alone would not.
    """
    returned = firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    assert isinstance(returned, str)
    assert returned == EXPECTED_DOCUMENT_ID


def test_add_tweet_returns_the_id_of_the_second_element(
    firestore_client, mock_add_result, mock_document_reference
):
    """The id comes from element 1 of the pair, never from element 0.

    Both elements carry an ``id``, and the two strings differ, so indexing the
    write timestamp instead of the document reference would surface
    :data:`UNRETURNED_ELEMENT_ID` here.
    """
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
    """``.add`` receives the caller's own object, exactly once.

    Identity is asserted, not equality: the subject performs no copy and no
    serialization, so the dict the caller passed is the dict the client is
    handed.
    """
    payload = dict(MINIMAL_TWEET_PAYLOAD)

    firestore.add_tweet(payload)

    mock_tweets_collection.add.assert_called_once_with(payload)
    assert mock_tweets_collection.add.call_args[0][0] is payload


def test_add_tweet_accepts_a_schema_valid_payload(
    mock_tweets_collection, mock_add_result
):
    """A full ten-field tweet payload reaches ``.add`` unmodified.

    Equality against a freshly built payload is what establishes "unmodified":
    ``make_tweet`` is deterministic and returns fresh containers, so a subject
    that mutated its argument would break the comparison.
    """
    payload = make_tweet()

    returned = firestore.add_tweet(payload)

    assert returned == EXPECTED_DOCUMENT_ID
    mock_tweets_collection.add.assert_called_once_with(payload)
    assert payload == make_tweet()


def test_add_tweet_does_not_read_the_document_snapshot(
    mock_tweets_collection, mock_add_result
):
    """``add_tweet`` writes through ``.add`` only.

    It never resolves a document reference of its own, so nothing on the
    ``.document(...)`` chain that ``get_tweet`` and ``update_tweet`` use is
    touched.
    """
    firestore.add_tweet(MINIMAL_TWEET_PAYLOAD)

    mock_tweets_collection.document.assert_not_called()


# --------------------------------------------------------------------------- #
# get_tweet -- lines 19-26.
# --------------------------------------------------------------------------- #


def test_get_tweet_returns_the_document_dictionary(mock_snapshot):
    """A present document yields the object ``to_dict()`` produced.

    Identity is asserted because line 24 returns that object directly, without
    copying or reshaping it.
    """
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
    """The id the caller passed is the id the document lookup uses."""
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
    """An absent document yields ``None``; the subject does not raise.

    Production returns ``None`` rather than signalling the miss, which is the
    divergence this case captures.  A caller therefore cannot distinguish an
    absent document from one whose contents are empty.
    """
    mock_snapshot.exists = exists

    returned = firestore.get_tweet(TWEET_ID)

    assert returned is None


def test_get_tweet_does_not_read_an_absent_document(mock_snapshot):
    """The ``else`` branch returns without consulting the snapshot's contents."""
    mock_snapshot.exists = False

    firestore.get_tweet(TWEET_ID)

    mock_snapshot.to_dict.assert_not_called()


def test_get_tweet_returns_a_falsy_dictionary_unchanged(mock_snapshot):
    """A present document whose contents are empty yields that empty ``dict``.

    The branch at line 23 tests ``doc.exists``, not the contents, so an empty
    mapping is returned as itself and is distinguishable from the ``None`` an
    absent document produces only by identity.
    """
    stored = {}
    mock_snapshot.to_dict.return_value = stored

    returned = firestore.get_tweet(TWEET_ID)

    assert returned is stored
    assert returned is not None


def test_get_tweet_does_not_write(mock_tweet_document, mock_snapshot):
    """``get_tweet`` is read-only: neither ``.add`` nor ``.update`` is called."""
    firestore.get_tweet(TWEET_ID)

    mock_tweet_document.update.assert_not_called()


# --------------------------------------------------------------------------- #
# update_tweet -- lines 28-37.
# --------------------------------------------------------------------------- #


def test_update_tweet_returns_true_on_success(mock_tweet_document):
    """A returning ``doc_ref.update`` yields ``True``.

    ``is True`` rather than a truthiness check, because line 35 returns the
    literal.
    """
    returned = firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    assert returned is True


def test_update_tweet_applies_the_update_payload(mock_tweet_document):
    """``.update`` receives the caller's own mapping, exactly once."""
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
    """A raising ``doc_ref.update`` yields ``False`` and nothing escapes.

    No ``pytest.raises`` guards this call: the assertion is that the exception
    does not propagate at all.  Were it to escape, the test would end in an
    error rather than a failure, which is the same signal.

    The bare ``except Exception`` at line 36 catches the narrower types as well
    as ``Exception`` itself, and discards each one silently — the subject logs
    nothing, binds no exception name and chains nothing, so the ``False`` return
    is the only observable evidence of the failure.
    """
    mock_tweet_document.update.side_effect = failure_type(message)

    returned = firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    assert returned is False


def test_update_tweet_attempts_the_write_before_failing(mock_tweet_document):
    """The ``False`` return follows a real attempt, not a short circuit."""
    mock_tweet_document.update.side_effect = Exception("boom")

    firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    mock_tweet_document.update.assert_called_once_with(UPDATE_PAYLOAD)


def test_update_tweet_does_not_read_the_document(mock_tweet_document):
    """``update_tweet`` writes blind: it never fetches the snapshot first.

    There is no read-modify-write and no existence check, so updating an id
    that does not exist is left entirely to the client's own behaviour.
    """
    firestore.update_tweet(TWEET_ID, UPDATE_PAYLOAD)

    mock_tweet_document.get.assert_not_called()


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
    """The wrappers drive the client ``get_db()`` returned.

    ``db`` at line 5 is a distinct object that no wrapper consults, which is
    what makes the patched factory the only boundary a test has to control.
    """
    firestore.get_tweet(TWEET_ID)

    assert firestore_client.collection.called
    assert firestore.db is not firestore_client


# --------------------------------------------------------------------------- #
# Module contract and recorded absences.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", PUBLIC_SURFACE)
def test_module_exposes_its_public_surface(firestore_client, name):
    """Each documented name is present on the subject."""
    assert hasattr(firestore, name)


@pytest.mark.parametrize("name", UNDEFINED_IMPORTED_NAMES)
def test_module_does_not_define_the_names_production_imports_from_it(
    firestore_client, name
):
    """``add_response`` is absent, although production imports it from here.

    ``app/tasks/response_generator.py`` line 1 does
    ``from app.db.firestore import get_tweet, add_response``, so that import
    resolves only under the fail-closed shim ``backend/tests/conftest.py``
    installs.  The shim binds the name onto this module for the lifetime of the
    ``response_generator_module`` fixture and deletes it on teardown, which is
    what makes this assertion independent of test order.

    Defining it is out of scope; this case is the gate that reports it if it
    ever appears.
    """
    assert not hasattr(firestore, name)


def test_module_level_client_is_a_firestore_client(firestore_client):
    """``db`` is a real client, constructed at import and used by nothing.

    ``google.cloud.firestore.Client`` defers every connection to its first RPC,
    so building it at module scope opens no socket and importing this subject is
    safe.  No test constructs one; this asserts the instance the import already
    produced.
    """
    assert isinstance(firestore.db, Client)


def test_get_tweet_is_not_a_coroutine_function(firestore_client):
    """``get_tweet`` is synchronous.

    ``app/tasks/response_generator.py`` line 12 awaits its result, which is a
    ``TypeError``; that suite asserts the error and this case pins the fact it
    depends on.
    """
    assert inspect.iscoroutinefunction(firestore.get_tweet) is False


@pytest.mark.parametrize("name", UNPATCHED_WRAPPERS)
def test_module_wrappers_are_synchronous(firestore_client, name):
    """No wrapper on the subject's surface is a coroutine function.

    The cases are :data:`UNPATCHED_WRAPPERS`.  ``get_db`` is not among them; the
    name is bound to a stand-in while every test in this module runs.
    """
    assert inspect.iscoroutinefunction(getattr(firestore, name)) is False


# --------------------------------------------------------------------------- #
# Structural gate.  Keeps the isolation guarantee true for tests added later.
# --------------------------------------------------------------------------- #


def _fixture_parameter_names(target):
    """Return the parameter names of a test function or fixture definition.

    ``@pytest.fixture`` returns a wrapper object rather than the function in
    pytest 8.4, and :func:`inspect.signature` reports the underlying parameters
    for both shapes.
    """
    return tuple(inspect.signature(target).parameters)


def _is_fixture(candidate):
    """Return whether ``candidate`` is a fixture defined in this module."""
    return any(
        hasattr(candidate, attribute) for attribute in FIXTURE_MARKER_ATTRIBUTES
    )


def _resolves_to_required_fixture(name, namespace, visited):
    """Return whether ``name`` is, or transitively requests, the client patch.

    A name that resolves to no fixture in ``namespace`` is a leaf: either a
    parametrised argument or a fixture defined in a conftest, neither of which
    can reach :data:`REQUIRED_ISOLATION_FIXTURE` through this module.
    """
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
    """Every test in this module has the client patch in its fixture closure.

    ``app.db.firestore.get_db`` resolves ambient credentials and constructs a
    real client, so a test that reached a wrapper without the patch would issue
    a live Cloud Firestore request rather than fail offline.  The egress guard in
    ``backend/tests/conftest.py`` is the backstop for that; this case is the
    gate, and it covers a test added later that forgets the fixture.

    The closure is computed transitively, so requesting ``mock_snapshot`` — or
    anything else in this module that leads to it — satisfies the requirement
    just as an explicit ``firestore_client`` parameter does.
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

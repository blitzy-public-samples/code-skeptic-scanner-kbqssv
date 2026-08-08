"""Unit suite for ``app/tasks/response_generator.py``, the async response task.

The subject declares two public coroutine functions, ``generate_response``
(line 11) and ``process_pending_responses`` (line 24), over four names bound at
module scope: ``get_tweet`` and ``add_response`` from ``app.db.firestore``,
``settings``, and the ``llm_service`` instance built on line 7.

Every case below is an error case.  The module has no reachable happy path:
line 12 awaits a synchronous function, line 16 awaits a method of a class no
production module defines, line 18 awaits a name no production module defines,
and line 25 calls ``get_tweet`` with a keyword its signature does not declare.

What this suite asserts
-----------------------
* An awaitable ``get_tweet`` resolving to any falsy value raises
  ``ValueError`` whose message is exactly ``"Tweet with id 1 not found"``,
  with the id interpolated from the argument.
* ``get_tweet`` is awaited exactly once, with the tweet id unchanged.
* ``add_response`` is never reached on that path, because the raise on line 14
  precedes line 18.
* A ``get_tweet`` that returns its value synchronously raises ``TypeError``
  carrying ``"can't be used in 'await' expression"``, and the message is not
  the tweet-not-found sentence, so line 13 is not what fired.
* ``process_pending_responses`` raises ``TypeError`` carrying
  ``"unexpected keyword argument 'response_status'"``.
* That failure happens while line 25 is being called, before any await:
  neither the Firestore client nor ``add_response`` is reached.
* ``add_response`` is absent from ``app.db.firestore`` and is present in the
  subject only as the stand-in ``backend/tests/conftest.py`` installs.
* ``generate_response`` and ``process_pending_responses`` are both coroutine
  functions.
* ``app.services.llm_service`` exposes no ``LLMService`` class, and its
  ``generate_response`` is not a coroutine function.
* ``get_tweet`` is the object ``app.db.firestore`` defines, bound into the
  subject by value at import.

Current behaviour captured as divergence
----------------------------------------
Line 12 awaits before line 13 tests falsiness.  The ``ValueError`` on line 14
is therefore reachable only while ``get_tweet`` resolves through an awaitable.
The real ``app.db.firestore.get_tweet`` is a plain ``def`` — pinned
independently by ``backend/tests/unit/test_db_firestore.py`` with an
``iscoroutinefunction`` assertion — so against production the ``await`` on
line 12 raises ``TypeError`` and the falsy branch never runs.  Both outcomes
are asserted here.

Line 16 awaits ``llm_service.generate_response``.
``app/services/llm_service.py`` declares no ``LLMService`` class at all and
exposes only the synchronous free function ``generate_response``, so line 16
could not succeed against the real module even with a tweet in hand.

Line 18 awaits ``add_response``, which ``app/db/firestore.py`` does not
define.  The legacy ``backend/tests/test_tasks.py`` patched
``save_response_to_db`` for this step; no production symbol corresponds to it.

Line 25 passes ``response_status="pending"`` to a function declaring the
single parameter ``tweet_id``, so ``process_pending_responses`` raises while
that call is being bound.  Lines 27 to 32 — the counter, the loop and the
return — are unreachable, and no test here exercises them.

Rate limiting is recorded as a skip: neither
``app/tasks/response_generator.py`` nor ``app/services/llm_service.py``
implements any.

Scope
-----
Every test drives the subject's two coroutine functions directly.  The module
comes from the ``response_generator_module`` fixture in
``backend/tests/conftest.py`` on every use: line 7 builds ``llm_service`` at
module scope, and that fixture evicts and reloads the module per test.  The
subject emits no diagnostic output, so no test captures logs or stdout.

Reasoning for every choice in this module: ``docs/testing/DECISION-LOG.md``.
``docs/testing/TRACEABILITY-MATRIX.md`` records the legacy constructs these
tests replace.
"""

import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.factories import make_tweet

pytestmark = pytest.mark.unit


# Oracles.  Every value below is read from the subject module, or is the text
# the interpreter produces when the subject runs.

#: Import path of the subject.  It loads only under the two stand-ins its
#: line 1 and line 3 need, which ``response_generator_module`` installs.
SUBJECT_MODULE = "app.tasks.response_generator"

FIRESTORE_MODULE = "app.db.firestore"

LLM_SERVICE_MODULE = "app.services.llm_service"

#: Name line 1 imports from ``app.db.firestore``, which defines it nowhere.
ABSENT_FIRESTORE_SYMBOL = "add_response"

#: Name line 3 imports from ``app.services.llm_service``, which defines it
#: nowhere.
ABSENT_LLM_SERVICE_SYMBOL = "LLMService"

#: Argument handed to ``generate_response``.  Line 14 interpolates it into the
#: message, so this constant and :data:`TWEET_NOT_FOUND_MESSAGE` move together.
MISSING_TWEET_ID = "1"

#: Line 14 rendered for :data:`MISSING_TWEET_ID`.
TWEET_NOT_FOUND_MESSAGE = "Tweet with id 1 not found"

#: Fragment of the ``TypeError`` CPython raises for ``await`` on a value that
#: is not awaitable.  On CPython 3.9 the whole sentence for line 12 reads
#: ``object dict can't be used in 'await' expression``; the leading type name
#: is whatever ``get_tweet`` returned, so only the invariant tail is matched.
AWAIT_TYPE_ERROR_FRAGMENT = "can't be used in 'await' expression"

#: Fragment of the ``TypeError`` raised while line 25 binds its call.  On
#: CPython 3.9 the whole sentence reads ``get_tweet() got an unexpected
#: keyword argument 'response_status'``; the qualifier before ``()`` differs
#: between interpreter versions, so only the invariant tail is matched.
UNEXPECTED_KEYWORD_FRAGMENT = "unexpected keyword argument 'response_status'"

#: Results line 13 treats alike.  ``None`` is what ``app/db/firestore.py``
#: line 26 returns for an absent document; ``{}`` is a falsy value that is not
#: ``None``, which is what makes line 13 a falsiness test and not an identity
#: test against the sentinel the data-access layer happens to use.
FALSY_GET_TWEET_RESULTS = (
    pytest.param(None, id="none"),
    pytest.param({}, id="empty-dict"),
)

#: The subject's declared async surface.
COROUTINE_FUNCTION_NAMES = ("generate_response", "process_pending_responses")

#: Reason carried by the one skipped test, naming the absent production
#: feature rather than the test that cannot run.
RATE_LIMIT_SKIP_REASON = (
    "No rate-limiting logic exists to assert: neither "
    "app/tasks/response_generator.py nor app/services/llm_service.py "
    "implements a throttle, a quota, a backoff or a call budget, and the "
    "module has no reachable happy path from which repeated calls could be "
    "counted."
)

#: Calls the skipped test would issue to observe a throttle.
RATE_LIMIT_PROBE_CALLS = 3


# Fixtures.  Shared infrastructure comes from backend/tests/conftest.py; the
# two below are specific to this module.  Both take the subject from
# ``response_generator_module``, so no test holds a module this file cached.


@pytest.fixture
def mock_awaitable_get_tweet(response_generator_module):
    """Replace the subject's ``get_tweet`` with an awaitable stand-in.

    The patch target is the attribute on the *subject* module, which bound the
    name with ``from app.db.firestore import get_tweet`` at line 1, and not
    ``app.db.firestore.get_tweet``.

    The stand-in is an :class:`unittest.mock.AsyncMock` whose result is
    ``None``, so the ``await`` on line 12 completes and line 13 receives that
    result.  A test varies it through ``return_value``.

    Yields the mock; the patch is undone when the test ends.
    """
    with patch.object(
        response_generator_module,
        "get_tweet",
        AsyncMock(name="get_tweet", return_value=None),
    ) as mock:
        yield mock


@pytest.fixture
def mock_synchronous_get_tweet(response_generator_module):
    """Replace the subject's ``get_tweet`` with a stand-in that returns a dict.

    The stand-in is a :class:`unittest.mock.MagicMock` whose result is the
    ``make_tweet()`` payload.  It reproduces both the shape and the synchronous
    return of ``app/db/firestore.py`` line 24.

    Yields the mock; the patch is undone when the test ends.
    """
    with patch.object(
        response_generator_module,
        "get_tweet",
        MagicMock(name="get_tweet", return_value=make_tweet()),
    ) as mock:
        yield mock


# generate_response -- line 13 finds the awaited result falsy.


@pytest.mark.parametrize("absent_tweet", FALSY_GET_TWEET_RESULTS)
async def test_generate_response_raises_value_error_when_the_tweet_is_absent(
    response_generator_module, mock_awaitable_get_tweet, absent_tweet
):
    """A falsy awaited result raises ``ValueError`` with line 14's message.

    ``None`` is what ``app/db/firestore.py`` line 26 answers for an absent
    document, and ``{}`` is falsy without being that sentinel.  Line 13 tests
    falsiness, so both take the same branch and render the same sentence.
    """
    mock_awaitable_get_tweet.return_value = absent_tweet

    with pytest.raises(ValueError) as excinfo:
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert str(excinfo.value) == TWEET_NOT_FOUND_MESSAGE


async def test_generate_response_awaits_get_tweet_once_with_the_tweet_id(
    response_generator_module, mock_awaitable_get_tweet
):
    """Line 12 awaits ``get_tweet`` once, with the argument unchanged."""
    with pytest.raises(ValueError):
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    mock_awaitable_get_tweet.assert_awaited_once_with(MISSING_TWEET_ID)


async def test_generate_response_does_not_add_a_response_when_absent(
    response_generator_module, mock_awaitable_get_tweet
):
    """The raise on line 14 precedes line 18, so ``add_response`` is unused.

    ``add_response`` is the stand-in ``backend/tests/conftest.py`` installs; a
    call count of zero is the observable evidence that control left the
    function before reaching it.
    """
    with pytest.raises(ValueError):
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert response_generator_module.add_response.call_count == 0


# generate_response -- line 12 awaits a value returned synchronously.


async def test_generate_response_raises_type_error_when_get_tweet_is_sync(
    response_generator_module, mock_synchronous_get_tweet
):
    """A synchronously returned payload makes the ``await`` on line 12 fail.

    ``app/db/firestore.py`` line 19 declares ``get_tweet`` with ``def`` and
    line 24 returns a ``dict``; ``backend/tests/unit/test_db_firestore.py``
    pins that synchronous declaration independently.  Line 12 awaits the
    result, so production reaches this ``TypeError`` and never line 13.

    The raised exception is exactly ``TypeError`` and its message is not
    line 14's sentence, so the falsy check is demonstrably not what fired.
    """
    with pytest.raises(TypeError) as excinfo:
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert type(excinfo.value) is TypeError
    assert AWAIT_TYPE_ERROR_FRAGMENT in str(excinfo.value)
    assert TWEET_NOT_FOUND_MESSAGE not in str(excinfo.value)


async def test_generate_response_does_not_add_a_response_when_await_fails(
    response_generator_module, mock_synchronous_get_tweet
):
    """Line 12 raises, so neither line 16 nor line 18 is reached."""
    with pytest.raises(TypeError):
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert response_generator_module.add_response.call_count == 0


# process_pending_responses -- line 25 supplies a keyword get_tweet has no
# parameter for.  These tests leave get_tweet unpatched, so the callable being
# bound is the one app/db/firestore.py declares.


async def test_process_pending_responses_raises_type_error_for_keyword(
    response_generator_module,
):
    """Line 25's ``response_status`` keyword has no matching parameter.

    ``app/db/firestore.py`` line 19 declares ``get_tweet(tweet_id: str)``.
    Binding the call on line 25 fails, so the coroutine raises before its first
    await and the message names the keyword that has no home.
    """
    with pytest.raises(TypeError) as excinfo:
        await response_generator_module.process_pending_responses()

    assert type(excinfo.value) is TypeError
    assert UNEXPECTED_KEYWORD_FRAGMENT in str(excinfo.value)


async def test_process_pending_responses_reaches_no_data_access_boundary(
    response_generator_module, firestore_client
):
    """Nothing downstream of line 25 runs.

    The failure happens while the call is being bound, so ``get_tweet``'s body
    never executes: it would have reached ``get_db()`` and then
    ``client.collection('tweets')``.  ``add_response`` is likewise untouched,
    which places the failure ahead of line 18 as well as ahead of line 12's
    await.
    """
    with pytest.raises(TypeError):
        await response_generator_module.process_pending_responses()

    assert firestore_client.collection.call_count == 0
    assert response_generator_module.add_response.call_count == 0


# Inherited stub.  Legacy backend/tests/test_tasks.py::
# test_generate_response_rate_limiting had a `pass` body; it is carried here as
# a skip whose reason names the production feature that does not exist.  The
# other two legacy stubs, media handling and deduplication, belong to
# backend/tests/unit/test_tasks_tweet_processor.py.


@pytest.mark.skip(reason=RATE_LIMIT_SKIP_REASON)
async def test_generate_response_rate_limiting(
    response_generator_module, mock_awaitable_get_tweet
):
    """Repeated generation would be throttled at a declared call budget.

    The body below is the assertion this suite would make.  It cannot run for
    two independent reasons, both recorded rather than worked around:
    ``RESPONSE_RATE_LIMIT`` names no attribute of the subject, because no
    throttle, quota, backoff or call budget is implemented in
    ``app/tasks/response_generator.py`` or ``app/services/llm_service.py``;
    and the loop has no reachable happy path to repeat, since line 16 awaits a
    method of a class no production module defines.
    """
    mock_awaitable_get_tweet.return_value = make_tweet()

    for _ in range(RATE_LIMIT_PROBE_CALLS):
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert (
        response_generator_module.add_response.call_count
        <= response_generator_module.RESPONSE_RATE_LIMIT
    )


# Recorded divergences.  Each asserts a property of the production modules
# themselves, which is what turns the missing-symbol claims in
# docs/testing/TRACEABILITY-MATRIX.md into verified facts.


def test_add_response_is_absent_from_the_firestore_module():
    """``app.db.firestore`` defines no ``add_response``.

    Line 1 of the subject imports the name from that module.  This test
    deliberately does not request ``response_generator_module``, so no
    stand-in is installed and the module is in its production shape.

    The legacy ``backend/tests/test_tasks.py`` patched
    ``backend.tasks.save_response_to_db`` for the persistence step; this is the
    assertion behind that mapping's "no production equivalent" verdict.
    """
    firestore = importlib.import_module(FIRESTORE_MODULE)

    assert not hasattr(firestore, ABSENT_FIRESTORE_SYMBOL)


def test_add_response_is_supplied_by_the_suite_stand_in(
    response_generator_module,
):
    """The subject's ``add_response`` is the stand-in, not a production symbol.

    ``backend/tests/conftest.py`` binds it on ``app.db.firestore`` for the
    duration of the fixture and the subject captures it at line 1, which is the
    only reason the module imports at all.  It is a
    :class:`unittest.mock.MagicMock`, so the call counts the tests above assert
    on are the stand-in's own.
    """
    firestore = importlib.import_module(FIRESTORE_MODULE)

    assert isinstance(response_generator_module.add_response, MagicMock)
    assert response_generator_module.add_response is getattr(
        firestore, ABSENT_FIRESTORE_SYMBOL
    )


def test_get_tweet_is_bound_from_the_firestore_module(
    response_generator_module,
):
    """The subject holds the function ``app.db.firestore`` defines.

    Line 1 binds it by value at import, so the object is the production one and
    the tests above replace it on the subject rather than on its definer.
    """
    firestore = importlib.import_module(FIRESTORE_MODULE)

    assert response_generator_module.get_tweet is firestore.get_tweet


@pytest.mark.parametrize("function_name", COROUTINE_FUNCTION_NAMES)
def test_module_declares_its_coroutine_surface(
    response_generator_module, function_name
):
    """Both public functions are coroutine functions."""
    assert inspect.iscoroutinefunction(
        getattr(response_generator_module, function_name)
    )


def test_llm_service_module_declares_no_llm_service_class():
    """``app.services.llm_service`` defines no ``LLMService``.

    Line 3 of the subject imports the name and line 7 instantiates it.  This
    test does not request ``response_generator_module``, so the module carries
    no stand-in and shows its production shape.
    """
    llm_service = importlib.import_module(LLM_SERVICE_MODULE)

    assert not hasattr(llm_service, ABSENT_LLM_SERVICE_SYMBOL)


def test_llm_service_generate_response_is_not_a_coroutine_function():
    """The only ``generate_response`` that module exposes is synchronous.

    Line 16 of the subject awaits ``llm_service.generate_response(...)``.  The
    free function ``app/services/llm_service.py`` line 10 declares with ``def``
    is the module's entire response-generating surface, so line 16 has neither
    a class to reach through nor an awaitable to await.
    """
    llm_service = importlib.import_module(LLM_SERVICE_MODULE)

    assert not inspect.iscoroutinefunction(llm_service.generate_response)

import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.factories import make_tweet

pytestmark = pytest.mark.unit


SUBJECT_MODULE = "app.tasks.response_generator"

FIRESTORE_MODULE = "app.db.firestore"

LLM_SERVICE_MODULE = "app.services.llm_service"

ABSENT_FIRESTORE_SYMBOL = "add_response"

ABSENT_LLM_SERVICE_SYMBOL = "LLMService"

MISSING_TWEET_ID = "1"

TWEET_NOT_FOUND_MESSAGE = "Tweet with id 1 not found"

#: Match only the invariant await TypeError suffix; CPython may vary the
#: leading type wording.
AWAIT_TYPE_ERROR_FRAGMENT = "can't be used in 'await' expression"

#: Match only the invariant unexpected-keyword suffix; callable qualification
#: may vary by CPython version.
UNEXPECTED_KEYWORD_FRAGMENT = "unexpected keyword argument 'response_status'"

FALSY_GET_TWEET_RESULTS = (
    pytest.param(None, id="none"),
    pytest.param({}, id="empty-dict"),
)

COROUTINE_FUNCTION_NAMES = ("generate_response", "process_pending_responses")

RATE_LIMIT_SKIP_REASON = (
    "Neither app/tasks/response_generator.py nor app/services/llm_service.py "
    "implements rate limiting."
)

RATE_LIMIT_PROBE_CALLS = 3


@pytest.fixture
def mock_awaitable_get_tweet(response_generator_module):
    """Patch the subject-bound get_tweet with AsyncMock so the post-await
    branch is reachable.
    """
    with patch.object(
        response_generator_module,
        "get_tweet",
        AsyncMock(name="get_tweet", return_value=None),
    ) as mock:
        yield mock


@pytest.fixture
def mock_synchronous_get_tweet(response_generator_module):
    with patch.object(
        response_generator_module,
        "get_tweet",
        MagicMock(name="get_tweet", return_value=make_tweet()),
    ) as mock:
        yield mock


@pytest.mark.parametrize("absent_tweet", FALSY_GET_TWEET_RESULTS)
async def test_generate_response_raises_value_error_when_the_tweet_is_absent(
    response_generator_module, mock_awaitable_get_tweet, absent_tweet
):
    mock_awaitable_get_tweet.return_value = absent_tweet

    with pytest.raises(ValueError) as excinfo:
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert str(excinfo.value) == TWEET_NOT_FOUND_MESSAGE


async def test_generate_response_awaits_get_tweet_once_with_the_tweet_id(
    response_generator_module, mock_awaitable_get_tweet
):
    with pytest.raises(ValueError):
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    mock_awaitable_get_tweet.assert_awaited_once_with(MISSING_TWEET_ID)


async def test_generate_response_does_not_add_a_response_when_absent(
    response_generator_module, mock_awaitable_get_tweet
):
    with pytest.raises(ValueError):
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert response_generator_module.add_response.call_count == 0


async def test_generate_response_raises_type_error_when_get_tweet_is_sync(
    response_generator_module, mock_synchronous_get_tweet
):
    with pytest.raises(TypeError) as excinfo:
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert type(excinfo.value) is TypeError
    assert AWAIT_TYPE_ERROR_FRAGMENT in str(excinfo.value)
    assert TWEET_NOT_FOUND_MESSAGE not in str(excinfo.value)


async def test_generate_response_does_not_add_a_response_when_await_fails(
    response_generator_module, mock_synchronous_get_tweet
):
    with pytest.raises(TypeError):
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert response_generator_module.add_response.call_count == 0


async def test_process_pending_responses_raises_type_error_for_keyword(
    response_generator_module,
):
    with pytest.raises(TypeError) as excinfo:
        await response_generator_module.process_pending_responses()

    assert type(excinfo.value) is TypeError
    assert UNEXPECTED_KEYWORD_FRAGMENT in str(excinfo.value)


async def test_process_pending_responses_reaches_no_data_access_boundary(
    response_generator_module, firestore_client
):
    with pytest.raises(TypeError):
        await response_generator_module.process_pending_responses()

    assert firestore_client.collection.call_count == 0
    assert response_generator_module.add_response.call_count == 0


@pytest.mark.skip(reason=RATE_LIMIT_SKIP_REASON)
async def test_generate_response_rate_limiting(
    response_generator_module, mock_awaitable_get_tweet
):
    mock_awaitable_get_tweet.return_value = make_tweet()

    for _ in range(RATE_LIMIT_PROBE_CALLS):
        await response_generator_module.generate_response(MISSING_TWEET_ID)

    assert (
        response_generator_module.add_response.call_count
        <= response_generator_module.RESPONSE_RATE_LIMIT
    )


def test_add_response_is_absent_from_the_firestore_module():
    firestore = importlib.import_module(FIRESTORE_MODULE)

    assert not hasattr(firestore, ABSENT_FIRESTORE_SYMBOL)


def test_add_response_is_supplied_by_the_suite_stand_in(
    response_generator_module,
):
    firestore = importlib.import_module(FIRESTORE_MODULE)

    assert isinstance(response_generator_module.add_response, MagicMock)
    assert response_generator_module.add_response is getattr(
        firestore, ABSENT_FIRESTORE_SYMBOL
    )


def test_get_tweet_is_bound_from_the_firestore_module(
    response_generator_module,
):
    firestore = importlib.import_module(FIRESTORE_MODULE)

    assert response_generator_module.get_tweet is firestore.get_tweet


@pytest.mark.parametrize("function_name", COROUTINE_FUNCTION_NAMES)
def test_module_declares_its_coroutine_surface(
    response_generator_module, function_name
):
    assert inspect.iscoroutinefunction(
        getattr(response_generator_module, function_name)
    )


def test_llm_service_module_declares_no_llm_service_class():
    llm_service = importlib.import_module(LLM_SERVICE_MODULE)

    assert not hasattr(llm_service, ABSENT_LLM_SERVICE_SYMBOL)


def test_llm_service_generate_response_is_not_a_coroutine_function():
    llm_service = importlib.import_module(LLM_SERVICE_MODULE)

    assert not inspect.iscoroutinefunction(llm_service.generate_response)

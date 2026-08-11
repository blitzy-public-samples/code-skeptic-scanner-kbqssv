from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.services.llm_service as llm_service
from app.schema.tweet import Tweet
from tests.factories import make_tweet

pytestmark = pytest.mark.unit


#: Patch app.services.llm_service.Completion.create because the subject imports
#: Completion directly.
COMPLETION_TARGET = "app.services.llm_service.Completion.create"

FALLBACK_SENTENCE = "Sorry, I couldn't generate a response at this time."

DIAGNOSTIC_PREFIX = "Error calling OpenAI API:"

UNDECLARED_ENGINE_FIELD = "openai_engine"

CONFIGURED_ENGINE = "text-davinci-003"

PADDED_COMPLETION_TEXT = "  hello  "

STRIPPED_COMPLETION_TEXT = "hello"

LITERAL_COMPLETION_KWARGS = {
    "max_tokens": 150,
    "n": 1,
    "stop": None,
    "temperature": 0.7,
}

COMPLETION_KWARG_NAMES = frozenset(
    {"engine", "prompt", "max_tokens", "n", "stop", "temperature"}
)

DUCK_CONTENT = "Copilot writes my tests for me"

DUCK_AUTHOR = "skeptic_dev"

DUCK_CREATED_AT = datetime(2024, 1, 1, 0, 0, 0)

TIMEOUT_MESSAGE = "timeout"


@pytest.fixture
def mock_tweet():
    return SimpleNamespace(
        content=DUCK_CONTENT,
        author=DUCK_AUTHOR,
        created_at=DUCK_CREATED_AT,
    )


@pytest.fixture
def engine_configured(monkeypatch):
    """Replace the subject-local settings with a stand-in exposing
    openai_engine; monkeypatch restores it.
    """
    stand_in = SimpleNamespace(openai_engine=CONFIGURED_ENGINE)
    monkeypatch.setattr(llm_service, "settings", stand_in)
    return stand_in


def test_module_exposes_generate_response_and_no_service_class():
    assert callable(llm_service.generate_response)
    assert not hasattr(llm_service, "LLMService")


def test_completion_endpoint_resolves_through_the_subject_only():
    assert isinstance(llm_service.Completion, type)
    assert not hasattr(llm_service, "openai")

    with pytest.raises(ModuleNotFoundError, match=r"is not a package"):
        with patch("app.services.llm_service.openai.Completion.create"):
            raise AssertionError(
                "the library-qualified target resolved; it must not resolve"
            )


def test_generate_response_rejects_the_annotated_schema_type():
    tweet = Tweet(**make_tweet())

    with pytest.raises(AttributeError, match="author"):
        llm_service.generate_response(tweet)


def test_generate_response_falls_back_when_engine_is_unconfigured(
    mock_tweet, capsys
):
    result = llm_service.generate_response(mock_tweet)

    assert result == FALLBACK_SENTENCE

    stdout = capsys.readouterr().out
    assert DIAGNOSTIC_PREFIX in stdout
    assert UNDECLARED_ENGINE_FIELD in stdout


def test_generate_response_swallows_a_completion_failure(
    mock_tweet, engine_configured, capsys
):
    with patch(
        COMPLETION_TARGET, side_effect=TimeoutError(TIMEOUT_MESSAGE)
    ) as mock_create:
        result = llm_service.generate_response(mock_tweet)

    assert result == FALLBACK_SENTENCE
    mock_create.assert_called_once()

    stdout = capsys.readouterr().out
    assert DIAGNOSTIC_PREFIX in stdout
    assert TIMEOUT_MESSAGE in stdout


def test_generate_response_returns_the_stripped_completion_text(
    mock_tweet, engine_configured, capsys
):
    completion = MagicMock(choices=[MagicMock(text=PADDED_COMPLETION_TEXT)])

    with patch(COMPLETION_TARGET, return_value=completion) as mock_create:
        result = llm_service.generate_response(mock_tweet)

    assert result == STRIPPED_COMPLETION_TEXT
    mock_create.assert_called_once()

    positional, keywords = mock_create.call_args
    assert positional == ()
    assert set(keywords) == COMPLETION_KWARG_NAMES
    assert keywords["engine"] == CONFIGURED_ENGINE
    assert keywords["engine"] == engine_configured.openai_engine
    assert {
        name: keywords[name] for name in LITERAL_COMPLETION_KWARGS
    } == LITERAL_COMPLETION_KWARGS

    prompt = keywords["prompt"]
    assert DUCK_CONTENT in prompt
    assert DUCK_AUTHOR in prompt
    assert str(DUCK_CREATED_AT) in prompt

    assert capsys.readouterr().out == ""


def test_generate_response_raises_on_an_empty_choice_list(
    mock_tweet, engine_configured
):
    completion = MagicMock(choices=[])

    with patch(COMPLETION_TARGET, return_value=completion) as mock_create:
        with pytest.raises(IndexError, match="list index out of range"):
            llm_service.generate_response(mock_tweet)

    mock_create.assert_called_once()

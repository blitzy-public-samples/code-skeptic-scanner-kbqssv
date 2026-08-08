"""Unit suite for ``app/services/llm_service.py``.

Covers the module's whole public surface -- the single free function
``generate_response`` -- across the five outcomes its control flow admits, and
the module contract that explains why ``backend/tests/conftest.py`` publishes an
``LLMService`` shim at all.

Where the ``try`` sits
----------------------
``generate_response`` builds a prompt from the tweet, calls the OpenAI
completion endpoint, and formats the result.  Only the middle step is guarded:
the ``try`` opens at line 17 and its ``except`` closes at line 29, so the prompt
construction at lines 12-14 and the completion indexing at line 32 are both
outside it.  The five outcome tests in this module are the five consequences.

==========================================  ==================================
Argument and configuration                  Outcome
==========================================  ==================================
a real ``Tweet``                            ``AttributeError`` for ``author``
duck object, ``openai_engine`` unset        diagnostic, fallback sentence
duck object, engine set, endpoint returns   the stripped completion text
duck object, engine set, endpoint raises    diagnostic, fallback sentence
duck object, engine set, ``choices == []``  ``IndexError``
==========================================  ==================================

Current behaviour captured as divergence
----------------------------------------
``app/schema/tweet.py`` declares neither ``author`` nor ``created_at``, so line
13 cannot succeed for the very type the signature annotates: a schema-valid
``Tweet`` never reaches the completion call.

Line 19 reads ``settings.openai_engine`` in lower case, while
``Settings.Config.case_sensitive`` is ``True`` and ``Settings`` declares no
field of any casing by that name.  The read therefore raises inside the ``try``
on every production call, and the completion branch at lines 32-37 is
unreachable outside a test.  :func:`engine_configured` is what reaches it here.

An exception raised by the completion endpoint is swallowed and answered with
the fallback sentence.  An empty ``choices`` list is not, because line 32 sits
after the ``except``.

Observability
-------------
The subject reports its swallowed failures with ``print()`` at line 28.  No
module under ``backend/app`` imports ``logging``, so that diagnostic is
observable only as captured stdout, which is what these tests read through
``capsys``.  The success path asserts that *nothing* is printed, so the
diagnostic is asserted from both sides.

Shared infrastructure
---------------------
``backend/tests/conftest.py`` seeds the environment before any ``app`` module is
imported, neutralises ambient Google credentials, and installs the
deny-by-default egress guard that would refuse a genuinely unmocked completion
call.  This module establishes none of them, and installs none of the import
shims that module publishes: the subject imports on its own.  Tweet payloads
come from ``backend/tests/factories.py``.

Reasoning for every choice in this module: ``docs/testing/DECISION-LOG.md``.
``docs/testing/TRACEABILITY-MATRIX.md`` records
``backend/tests/test_services.py::TestLLMService::test_generate_response`` as
the legacy construct this suite replaces.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.services.llm_service as llm_service
from app.schema.tweet import Tweet
from tests.factories import make_tweet

pytestmark = pytest.mark.unit

# Oracles.  Every value below is quoted from ``app/services/llm_service.py``
# or is a fixed input this module supplies.

#: Patch target for the completion endpoint: the name line 1 binds into the
#: subject's own namespace.  ``backend/tests/README.md`` publishes this string
#: as the OpenAI boundary, and every patch in this module uses it.
COMPLETION_TARGET = "app.services.llm_service.Completion.create"

#: Sentence line 29 returns for every failure the ``try`` catches, quoted from
#: the source with its apostrophe intact.
FALLBACK_SENTENCE = "Sorry, I couldn't generate a response at this time."

#: Prefix of the diagnostic line 28 prints before returning
#: :data:`FALLBACK_SENTENCE`.  The remainder of that line is ``str(e)``.
DIAGNOSTIC_PREFIX = "Error calling OpenAI API:"

#: Field name line 19 reads off ``settings``.  ``Settings`` does not declare
#: it, so the name appears in the diagnostic of
#: :func:`test_generate_response_falls_back_when_engine_is_unconfigured`.
UNDECLARED_ENGINE_FIELD = "openai_engine"

#: Value :func:`engine_configured` publishes as ``settings.openai_engine`` and
#: line 19 forwards as the ``engine`` keyword.
CONFIGURED_ENGINE = "text-davinci-003"

#: Completion text the patched endpoint returns.  Line 32 strips it.
PADDED_COMPLETION_TEXT = "  hello  "

#: :data:`PADDED_COMPLETION_TEXT` after line 32's ``strip()``.
STRIPPED_COMPLETION_TEXT = "hello"

#: The four keywords lines 21-24 pass as literals, so their values are fixed
#: for every call the subject makes.
LITERAL_COMPLETION_KWARGS = {
    "max_tokens": 150,
    "n": 1,
    "stop": None,
    "temperature": 0.7,
}

#: Every keyword lines 19-24 pass, and the complete set: the subject passes no
#: positional argument to the endpoint.
COMPLETION_KWARG_NAMES = frozenset(
    {"engine", "prompt", "max_tokens", "n", "stop", "temperature"}
)

#: ``content`` of the duck object, read by line 12.
DUCK_CONTENT = "Copilot writes my tests for me"

#: ``author`` of the duck object, read by line 13.
DUCK_AUTHOR = "skeptic_dev"

#: ``created_at`` of the duck object, read by line 13 and interpolated into the
#: prompt as ``str(created_at)``.  A fixed instant, so the rendered prompt is
#: identical on every run.
DUCK_CREATED_AT = datetime(2024, 1, 1, 0, 0, 0)

#: Text of the exception the swallowed-failure test makes the endpoint raise.
#: Line 28 prints it as ``str(e)``.
TIMEOUT_MESSAGE = "timeout"


@pytest.fixture
def mock_tweet():
    """Return a duck object standing in for the subject's argument.

    Exposes exactly ``content``, ``author`` and ``created_at`` -- the three
    attributes lines 12 and 13 read -- and nothing else.  ``created_at`` is a
    fixed :class:`datetime.datetime`, so the prompt the subject renders is
    byte-identical on every run and no assertion here reads the clock.

    :returns: A :class:`types.SimpleNamespace` carrying
        :data:`DUCK_CONTENT`, :data:`DUCK_AUTHOR` and :data:`DUCK_CREATED_AT`.
    """
    return SimpleNamespace(
        content=DUCK_CONTENT,
        author=DUCK_AUTHOR,
        created_at=DUCK_CREATED_AT,
    )


@pytest.fixture
def engine_configured(monkeypatch):
    """Publish ``settings.openai_engine`` for the duration of one test.

    ``app/services/llm_service.py`` line 5 builds its own ``Settings`` instance
    and line 19 reads ``openai_engine`` off it at call time.  ``Settings``
    declares no such field, and pydantic v1 refuses to set an undeclared field
    on an instance.

    This fixture replaces the module attribute with a stand-in exposing the one
    field line 19 reads.  ``monkeypatch`` restores the real instance when the
    test ends, so the attribute is absent again for
    :func:`test_generate_response_falls_back_when_engine_is_unconfigured`
    whatever order the two run in.

    :returns: The :class:`types.SimpleNamespace` stand-in, whose
        ``openai_engine`` is :data:`CONFIGURED_ENGINE`.
    """
    stand_in = SimpleNamespace(openai_engine=CONFIGURED_ENGINE)
    monkeypatch.setattr(llm_service, "settings", stand_in)
    return stand_in


# Module contract.


def test_module_exposes_generate_response_and_no_service_class():
    """The subject's public surface is one free function and no class.

    ``generate_response`` is present and callable, and no ``LLMService`` exists.
    ``app/tasks/tweet_processor.py`` line 4 and
    ``app/tasks/response_generator.py`` line 3 both import that missing name,
    which is the ``ImportError`` the shim published by
    ``backend/tests/conftest.py`` stands in for.
    """
    assert callable(llm_service.generate_response)
    assert not hasattr(llm_service, "LLMService")


def test_completion_endpoint_resolves_through_the_subject_only():
    """:data:`COMPLETION_TARGET` resolves; the library-qualified target does not.

    Line 1 is ``from openai import Completion``, so the subject binds the class
    and never the name ``openai``.  A dotted patch target's leading segments are
    imported before the final attribute is fetched, so a target routed through
    ``app.services.llm_service.openai`` is reported as a missing module.
    """
    assert isinstance(llm_service.Completion, type)
    assert not hasattr(llm_service, "openai")

    with pytest.raises(ModuleNotFoundError, match=r"is not a package"):
        with patch("app.services.llm_service.openai.Completion.create"):
            raise AssertionError(
                "the library-qualified target resolved; it must not resolve"
            )


# Outcome 1 -- the prompt's context clause, read before the ``try``.


def test_generate_response_rejects_the_annotated_schema_type():
    """A schema-valid ``Tweet`` raises ``AttributeError`` naming ``author``.

    ``generate_response`` annotates its parameter ``Tweet``, and line 13 reads
    ``author`` and ``created_at``, neither of which ``app/schema/tweet.py``
    declares.  That read precedes the ``try`` at line 17, so the error
    propagates instead of becoming :data:`FALLBACK_SENTENCE`.
    """
    tweet = Tweet(**make_tweet())

    with pytest.raises(AttributeError, match="author"):
        llm_service.generate_response(tweet)


# Outcomes 2 and 4 -- failures the ``try`` catches.


def test_generate_response_falls_back_when_engine_is_unconfigured(
    mock_tweet, capsys
):
    """An unconfigured ``openai_engine`` yields the fallback sentence.

    Line 19 reads ``openai_engine`` off the ``Settings`` instance the subject
    builds at line 5, which declares no such field.  That read is the first
    statement inside the ``try``, so line 28 prints the diagnostic -- naming the
    missing field -- and line 29 returns :data:`FALLBACK_SENTENCE`.

    The endpoint is not patched here.  The failure occurs while the ``engine``
    keyword is being evaluated, so no call is made and no network boundary is
    reached.
    """
    result = llm_service.generate_response(mock_tweet)

    assert result == FALLBACK_SENTENCE

    stdout = capsys.readouterr().out
    assert DIAGNOSTIC_PREFIX in stdout
    assert UNDECLARED_ENGINE_FIELD in stdout


def test_generate_response_swallows_a_completion_failure(
    mock_tweet, engine_configured, capsys
):
    """An exception from the endpoint becomes the fallback sentence.

    The call at lines 18-25 sits inside the ``try``, so a ``TimeoutError``
    raised by the endpoint is caught: line 28 prints the diagnostic followed by
    the exception's own text, line 29 returns :data:`FALLBACK_SENTENCE`, and
    nothing propagates to the caller.
    """
    with patch(
        COMPLETION_TARGET, side_effect=TimeoutError(TIMEOUT_MESSAGE)
    ) as mock_create:
        result = llm_service.generate_response(mock_tweet)

    assert result == FALLBACK_SENTENCE
    mock_create.assert_called_once()

    stdout = capsys.readouterr().out
    assert DIAGNOSTIC_PREFIX in stdout
    assert TIMEOUT_MESSAGE in stdout


# Outcome 3 -- the completion branch, reachable only under test.


def test_generate_response_returns_the_stripped_completion_text(
    mock_tweet, engine_configured, capsys
):
    """A successful completion is returned with its whitespace stripped.

    Line 32 indexes the first choice and strips its ``text``, turning
    :data:`PADDED_COMPLETION_TEXT` into :data:`STRIPPED_COMPLETION_TEXT`, and
    line 37 returns it unchanged.

    The endpoint is called exactly once, entirely by keyword, with the four
    literals of lines 21-24, the engine :func:`engine_configured` published, and
    a prompt carrying the three attributes lines 12 and 13 read.  The prompt is
    asserted by substring.

    Nothing is printed: line 28 is reachable only through the ``except``.
    """
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


# Outcome 5 -- the completion indexing, performed after the ``except``.


def test_generate_response_raises_on_an_empty_choice_list(
    mock_tweet, engine_configured
):
    """An empty ``choices`` list raises ``IndexError``.

    The endpoint returns successfully, so the ``try`` is left by falling off its
    end.  Line 32 then indexes ``choices[0]`` with the ``except`` already
    closed, and the ``IndexError`` propagates instead of becoming
    :data:`FALLBACK_SENTENCE`.
    """
    completion = MagicMock(choices=[])

    with patch(COMPLETION_TARGET, return_value=completion) as mock_create:
        with pytest.raises(IndexError, match="list index out of range"):
            llm_service.generate_response(mock_tweet)

    mock_create.assert_called_once()

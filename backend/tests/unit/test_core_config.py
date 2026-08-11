"""Unit suite for ``app/core/config.py``: the backend configuration
contract.

``app/core/config.py`` declares one pydantic v1 ``BaseSettings`` subclass,
``Settings``, and instantiates it once at module scope as ``settings``.
The values pinned here are the oracles the rest of the backend suite
asserts against.

What this module asserts
------------------------
Declared defaults
    The fallback value of every field ``Settings`` declares with a default, and
    the three attributes of the nested ``Settings.Config``.
Required fields
    That each of the eight fields declared *without* a default is genuinely
    required, that omitting one raises ``pydantic.ValidationError`` naming that
    field, and that the required set contains exactly those eight names.
    ``NOTION_API_KEY`` is declared ``Optional[str] = None``, so it is asserted
    to be optional rather than counted among them.
The shared singleton
    That ``app.core.config.settings`` is a ``Settings`` instance and that each
    required field on it carries the exact value the environment supplied,
    which is the environment-over-default precedence every other backend
    module depends on.
Class-versus-instance access
    That reading a declared field off the ``Settings`` *class* raises
    ``AttributeError``, because pydantic v1 moves declared fields out of
    the class namespace into ``Settings.__fields__``.
Fields declared for testability
    That ``ALLOWED_ORIGINS``, ``ALGORITHM``, ``PROJECT_ID`` and
    ``TWITTER_TRACK_KEYWORDS`` carry their least-privilege defaults, and
    that ``TWITTER_CONSUMER_KEY`` and ``TWITTER_CONSUMER_SECRET`` remain
    undeclared.

Isolation
---------
``Settings`` is a ``BaseSettings`` subclass, so a field's value comes from the
process environment, then from the ``.env`` file named by
``Settings.Config.env_file``, and only then from the value declared in the
class body. Assertions here are split along that precedence, and none of them
depends on a variable happening to be absent from the surrounding environment:

* An assertion about a **declared** value runs against a ``Settings`` built by
  :func:`_construct_settings`, which unsets the names under test and passes
  ``_env_file=None``, so neither an exported variable nor a developer's local
  ``.env`` contributes.
* An assertion about the value the shared **singleton** carries rests on
  ``backend/tests/conftest.py`` having assigned that value to the process
  environment at its own module scope, before ``app.core.config`` was imported.
  The process environment outranks the ``.env`` source, so the assignment
  decides the field.
  :func:`test_singleton_fields_are_pinned_by_the_test_prologue` asserts that
  precondition directly, through the ``pinned_settings_env`` fixture.
* ``NOTION_API_KEY`` is declared ``None``, a value no environment string can
  express, so it is asserted from ``Settings.__fields__`` and from an isolated
  construction only — never from a singleton. The prologue removes the name
  from the environment.

This module imports ``app.core.config`` and nothing else from ``app``. Shared
setup — the environment normalisation, the Google credential neutraliser and
the network guard — comes from ``backend/tests/conftest.py``.
"""

import os

import pytest
from pydantic import ValidationError

import app.core.config as config_module
from app.core.config import Settings
from tests.conftest import (
    REQUIRED_SETTINGS_ENV,
    TESTABILITY_SETTINGS_VALUES,
)

pytestmark = pytest.mark.unit


# The contract this suite pins.  Every literal below is read from
# ``app/core/config.py``; none is recomputed from the model.

#: The eight fields ``Settings`` declares without a default.
#: ``NOTION_API_KEY`` is declared ``Optional[str] = None`` and is not one
#: of them.
REQUIRED_FIELD_NAMES = (
    "SECRET_KEY",
    "TWITTER_API_KEY",
    "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN",
    "TWITTER_ACCESS_TOKEN_SECRET",
    "OPENAI_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "BIGQUERY_DATASET",
)

#: pydantic v1's ``type`` for an error raised because a field has neither a
#: supplied value nor a default.
MISSING_FIELD_ERROR_TYPE = "value_error.missing"

#: The two threshold constants other backend suites derive their expected
#: values from.
POPULARITY_THRESHOLD_DEFAULT = 100
DOUBT_RATING_THRESHOLD_DEFAULT = 0.7

#: Remaining defaulted fields, paired with the default each declares.
#: ``NOTION_API_KEY`` is asserted separately, for identity with ``None``.
SINGLETON_FIELD_DEFAULTS = (
    ("PROJECT_NAME", "Twitter Bot"),
    ("API_V1_STR", "/api/v1"),
    ("ACCESS_TOKEN_EXPIRE_MINUTES", 30),
    ("FIRESTORE_COLLECTION_TWEETS", "tweets"),
    ("FIRESTORE_COLLECTION_USERS", "users"),
    ("FIRESTORE_COLLECTION_RESPONSES", "responses"),
)

#: Every field whose value this suite reads from ``config_module.settings``.
#: ``NOTION_API_KEY`` is absent: its declared value is ``None``,
#: so the prologue removes the name instead of pinning it and
#: :func:`test_notion_api_key_declared_default_is_none` and
#: :func:`test_settings_omits_notion_api_key` carry that field.
SINGLETON_ASSERTED_FIELD_NAMES = tuple(
    [name for name, _ in SINGLETON_FIELD_DEFAULTS]
    + [
        "POPULARITY_THRESHOLD",
        "DOUBT_RATING_THRESHOLD",
    ]
)

#: The eight required fields paired with the value
#: ``backend/tests/conftest.py`` assigns to the environment for the whole
#: session.  Those assignments are unconditional, so each pair is the exact
#: value the shared ``settings`` singleton was built from.
REQUIRED_FIELD_SEEDED_VALUES = tuple(
    (name, REQUIRED_SETTINGS_ENV[name]) for name in REQUIRED_FIELD_NAMES
)

#: The two string attributes of the nested ``Settings.Config``.  ``Config`` is
#: a plain nested class rather than a field, so class access resolves.  The
#: third attribute, ``case_sensitive``, is covered by
#: :func:`test_settings_config_case_sensitive`, which asserts identity with
#: ``True``.
CONFIG_ATTRIBUTE_EXPECTATIONS = (
    ("env_file", ".env"),
    ("env_file_encoding", "utf-8"),
)

#: The four fields declared so the application object can be constructed
#: under test, paired with the least-privilege default each carries.
TESTABILITY_FIELD_DEFAULTS = (
    ("ALLOWED_ORIGINS", []),
    ("ALGORITHM", "HS256"),
    ("PROJECT_ID", ""),
    ("TWITTER_TRACK_KEYWORDS", []),
)

TESTABILITY_FIELD_NAMES = tuple(name for name, _ in TESTABILITY_FIELD_DEFAULTS)

#: Read by ``app/services/twitter_service.py`` and
#: ``app/tasks/tweet_processor.py``, declared by ``Settings`` nowhere.
UNDECLARED_CONSUMER_FIELD_NAMES = (
    "TWITTER_CONSUMER_KEY",
    "TWITTER_CONSUMER_SECRET",
)


# Shared helper.  The environment isolation lives here and nowhere else in
# this module.


def _construct_settings(monkeypatch, absent_fields=()):
    """Build a ``Settings`` with ``absent_fields`` unset and no ``.env``
    read.

    ``monkeypatch.delenv`` restores the previous value when the test ends,
    so no test mutates ``os.environ`` itself.  ``_env_file=None`` overrides
    ``Settings.Config.env_file`` for this construction, so a ``.env`` on
    disk contributes nothing.

    Propagates ``ValidationError`` when a required field is left with no
    value.
    """
    for field_name in absent_fields:
        monkeypatch.delenv(field_name, raising=False)
    return Settings(_env_file=None)


# Declared constants.


def test_popularity_threshold_declared_default(monkeypatch):
    """``POPULARITY_THRESHOLD`` declares 100 in the class body.

    Read from a ``Settings`` built with the name unset and the ``.env`` source
    disabled, so the assertion observes the declared value itself.
    """
    settings = _construct_settings(
        monkeypatch, absent_fields=("POPULARITY_THRESHOLD",)
    )

    assert settings.POPULARITY_THRESHOLD == POPULARITY_THRESHOLD_DEFAULT


def test_popularity_threshold_default():
    """``POPULARITY_THRESHOLD`` is 100 on the shared settings singleton.

    ``TweetStreamListener.on_status`` compares
    ``retweet_count + favorite_count`` against this field and returns early
    when the sum is lower, so this value is the oracle the tweet-processor
    suite parametrises its 99 / 100 / 101 matrix around. The parent conftest
    pins the environment variable of the same name to ``"100"`` before
    ``app.core.config`` is imported, which is what fixes the value the
    singleton carries.
    """
    assert config_module.settings.POPULARITY_THRESHOLD == POPULARITY_THRESHOLD_DEFAULT


def test_doubt_rating_threshold_declared_default(monkeypatch):
    """``DOUBT_RATING_THRESHOLD`` declares 0.7 in the class body."""
    settings = _construct_settings(
        monkeypatch, absent_fields=("DOUBT_RATING_THRESHOLD",)
    )

    assert settings.DOUBT_RATING_THRESHOLD == DOUBT_RATING_THRESHOLD_DEFAULT


def test_doubt_rating_threshold_default():
    """``DOUBT_RATING_THRESHOLD`` is 0.7 on the shared settings singleton.

    Asserted as a configuration constant only: no production module reads
    this field, so no gate anywhere compares a doubt rating against it.
    """
    assert config_module.settings.DOUBT_RATING_THRESHOLD == DOUBT_RATING_THRESHOLD_DEFAULT


@pytest.mark.parametrize(
    ("field_name", "expected_default"),
    SINGLETON_FIELD_DEFAULTS,
    ids=[name for name, _ in SINGLETON_FIELD_DEFAULTS],
)
def test_settings_declared_default(monkeypatch, field_name, expected_default):
    """``field_name`` declares ``expected_default`` in the class body.

    Built with ``field_name`` unset and ``_env_file=None``, so the value comes
    from the declaration rather than from the environment or from a ``.env``.
    """
    settings = _construct_settings(monkeypatch, absent_fields=(field_name,))

    assert getattr(settings, field_name) == expected_default


@pytest.mark.parametrize(
    ("field_name", "expected_default"),
    SINGLETON_FIELD_DEFAULTS,
    ids=[name for name, _ in SINGLETON_FIELD_DEFAULTS],
)
def test_settings_default_on_singleton(field_name, expected_default):
    """``field_name`` carries ``expected_default`` on the singleton.

    These are the values every other backend module sees, because each reads
    them from ``app.core.config.settings`` or from a ``Settings()`` of its own.
    The parent conftest pins each one in the process environment before the
    first ``app.core.config`` import.
    """
    assert getattr(config_module.settings, field_name) == expected_default


def test_notion_api_key_declared_default_is_none():
    """``NOTION_API_KEY`` declares ``None`` and is not required.

    Read from ``Settings.__fields__``, which no environment variable and no
    ``.env`` entry can shadow. Asserted with ``is`` rather than ``==`` so an
    empty string or any other falsy value cannot satisfy it.
    """
    field = Settings.__fields__["NOTION_API_KEY"]

    assert field.default is None
    assert field.required is False


def test_singleton_fields_are_pinned_by_the_test_prologue(pinned_settings_env):
    """Every singleton-asserted field has a value pinned in the environment.

    ``Settings`` resolves each field from the process environment before the
    ``.env`` source and before the declared value, so the pinned variable is
    what decides the value that :func:`test_settings_default_on_singleton`,
    :func:`test_popularity_threshold_default` and
    :func:`test_doubt_rating_threshold_default` read. This asserts that
    precondition positively: each name is present and carries the value
    ``backend/tests/conftest.py`` assigned, whatever the surrounding machine
    exported.

    ``NOTION_API_KEY`` is asserted absent, which is the other half of the same
    contract: no singleton assertion reads that field.
    """
    unpinned = sorted(
        name
        for name in SINGLETON_ASSERTED_FIELD_NAMES
        if os.environ.get(name) != pinned_settings_env.get(name)
    )

    assert unpinned == []
    assert "NOTION_API_KEY" not in os.environ


# The nested ``Settings.Config``.


@pytest.mark.parametrize(
    ("attribute_name", "expected_value"),
    CONFIG_ATTRIBUTE_EXPECTATIONS,
    ids=[name for name, _ in CONFIG_ATTRIBUTE_EXPECTATIONS],
)
def test_settings_config_attribute(attribute_name, expected_value):
    assert getattr(Settings.Config, attribute_name) == expected_value


def test_settings_config_case_sensitive():
    assert Settings.Config.case_sensitive is True


# Required fields.  One parametrised case per field, so each case reports
# independently.


@pytest.mark.parametrize("field_name", REQUIRED_FIELD_NAMES)
def test_settings_requires_field(monkeypatch, field_name):
    with pytest.raises(ValidationError) as raised:
        _construct_settings(monkeypatch, absent_fields=(field_name,))

    reported = [
        (error["loc"], error["type"]) for error in raised.value.errors()
    ]

    assert ((field_name,), MISSING_FIELD_ERROR_TYPE) in reported


def test_settings_omits_notion_api_key(monkeypatch):
    settings = _construct_settings(
        monkeypatch, absent_fields=("NOTION_API_KEY",)
    )

    assert settings.NOTION_API_KEY is None


def test_required_field_set_is_exactly_the_declared_eight():
    required_fields = {
        name
        for name, field in Settings.__fields__.items()
        if field.required
    }

    assert required_fields == set(REQUIRED_FIELD_NAMES)


# Class access versus instance access.


def test_class_access_google_cloud_project_raises_attribute_error():
    """Class access to ``GOOGLE_CLOUD_PROJECT`` raises ``AttributeError``.

    Class access, not instance access: the name resolves normally on
    ``config_module.settings``.  pydantic v1 moves declared fields out of
    the class namespace into ``Settings.__fields__``.

    ``app/db/bigquery.py`` performs exactly this class-level read twice,
    which is why ``get_bq_client``, ``run_query`` and
    ``insert_tweet_analytics`` are unreachable until a test substitutes the
    name.  Declaring further instance fields does not change it.
    """
    assert "GOOGLE_CLOUD_PROJECT" in Settings.__fields__
    assert (
        config_module.settings.GOOGLE_CLOUD_PROJECT
        == REQUIRED_SETTINGS_ENV["GOOGLE_CLOUD_PROJECT"]
    )

    with pytest.raises(AttributeError):
        getattr(Settings, "GOOGLE_CLOUD_PROJECT")


def test_class_access_defaulted_field_raises_attribute_error():
    """Class access raises for a field that declares a default as well.

    ``POPULARITY_THRESHOLD`` declares ``= 100`` and reading it off the
    class still raises, so the behaviour belongs to every pydantic v1
    field rather than only to the ones declared without a default.
    """
    assert (
        Settings.__fields__["POPULARITY_THRESHOLD"].default
        == POPULARITY_THRESHOLD_DEFAULT
    )

    with pytest.raises(AttributeError):
        getattr(Settings, "POPULARITY_THRESHOLD")


# Fields declared so the application object can be constructed under test.
# ``configure_cors`` reads ``ALLOWED_ORIGINS``, ``create_access_token``
# reads ``ALGORITHM``, ``firestore.get_db`` reads ``PROJECT_ID`` and both
# stream starters read ``TWITTER_TRACK_KEYWORDS``.  Each assertion below
# runs against a ``Settings`` built with all four names unset.


@pytest.mark.parametrize(
    ("field_name", "expected_default"),
    TESTABILITY_FIELD_DEFAULTS,
    ids=TESTABILITY_FIELD_NAMES,
)
def test_testability_field_default(monkeypatch, field_name, expected_default):
    settings = _construct_settings(
        monkeypatch, absent_fields=TESTABILITY_FIELD_NAMES
    )

    assert getattr(settings, field_name) == expected_default


@pytest.mark.parametrize(
    ("field_name", "expected_default"),
    TESTABILITY_FIELD_DEFAULTS,
    ids=TESTABILITY_FIELD_NAMES,
)
def test_testability_field_on_singleton(field_name, expected_default):
    """``field_name`` carries its least-privilege value on the singleton.

    ``configure_cors`` reads ``ALLOWED_ORIGINS`` from a settings instance,
    ``create_access_token`` reads ``ALGORITHM``, ``firestore.get_db`` reads
    ``PROJECT_ID`` and both stream starters read ``TWITTER_TRACK_KEYWORDS``, so
    these are the values the integration, security and stream suites observe.
    The parent conftest pins all four in the process environment.
    """
    assert getattr(config_module.settings, field_name) == expected_default


def test_project_id_is_not_an_alias_of_google_cloud_project():
    """``PROJECT_ID`` and ``GOOGLE_CLOUD_PROJECT`` are declared
    independently.

    ``PROJECT_ID`` declares an empty-string default while
    ``GOOGLE_CLOUD_PROJECT`` declares none and is required.  Asserted on
    the declarations, which no environment can shadow; the two can still
    hold equal values if the environment supplies them.
    """
    assert Settings.__fields__["PROJECT_ID"].default == ""
    assert Settings.__fields__["GOOGLE_CLOUD_PROJECT"].required is True
    assert Settings.__fields__["GOOGLE_CLOUD_PROJECT"].default is None


def test_project_id_does_not_resolve_to_google_cloud_project(monkeypatch):
    """A defaulted ``PROJECT_ID`` differs from a populated
    ``GOOGLE_CLOUD_PROJECT``.

    With ``PROJECT_ID`` unset the field falls back to the empty string while
    ``GOOGLE_CLOUD_PROJECT`` carries the value the environment supplies, so the
    two resolve differently on the same instance. Both sides are asserted
    against known values rather than against each other's truthiness.
    """
    settings = _construct_settings(
        monkeypatch, absent_fields=TESTABILITY_FIELD_NAMES
    )

    assert (
        settings.GOOGLE_CLOUD_PROJECT
        == REQUIRED_SETTINGS_ENV["GOOGLE_CLOUD_PROJECT"]
    )
    assert settings.PROJECT_ID == ""
    assert settings.PROJECT_ID != settings.GOOGLE_CLOUD_PROJECT


@pytest.mark.parametrize("field_name", TESTABILITY_FIELD_NAMES)
def test_testability_field_is_declared(field_name):
    assert field_name in Settings.__fields__


@pytest.mark.parametrize("field_name", UNDECLARED_CONSUMER_FIELD_NAMES)
def test_consumer_field_is_not_declared(field_name):
    """``field_name`` is read by production code but declared nowhere.

    ``start_twitter_stream`` and ``start_tweet_stream`` both read this
    name, so each raises ``AttributeError`` on the settings instance unless
    a test supplies it with ``monkeypatch``.
    """
    assert field_name not in Settings.__fields__

"""Unit suite for ``app/core/config.py``: the backend configuration contract.

``app/core/config.py`` declares one pydantic v1 ``BaseSettings`` subclass,
``Settings``, and instantiates it once at module scope as ``settings``. Other
backend modules read their configuration from that singleton and several
construct a ``Settings()`` of their own, so the values pinned here are the
oracles the rest of the backend suite asserts against — most directly
``POPULARITY_THRESHOLD``, which the tweet-processor suite parametrises its
popularity matrix around, and ``TWITTER_TRACK_KEYWORDS``, which the same suite
asserts as the ``track`` keyword handed to ``stream.filter``.

What this module asserts
------------------------
Declared defaults
    The effective value of every field ``Settings`` declares with a default,
    and the three attributes of the nested ``Settings.Config``.
Required fields
    That each of the eight fields declared *without* a default is genuinely
    required, that omitting one raises ``pydantic.ValidationError`` naming that
    field, and that the required set contains exactly those eight names.
    ``NOTION_API_KEY`` is declared ``Optional[str] = None``, so it is asserted
    to be optional rather than counted among them.
Class-versus-instance access
    That reading a declared field off the ``Settings`` *class* raises
    ``AttributeError``. pydantic v1 moves declared fields out of the class
    namespace into ``Settings.__fields__``, so the attribute does not exist on
    the class even though it resolves on an instance. This is the root cause of
    the ``app/db/bigquery.py`` failures: that module reads
    ``Settings.GOOGLE_CLOUD_PROJECT`` at class level twice, and declaring
    further instance fields cannot make those reads resolve.
Fields declared for testability
    That ``ALLOWED_ORIGINS``, ``ALGORITHM``, ``PROJECT_ID`` and
    ``TWITTER_TRACK_KEYWORDS`` are declared fields carrying their
    least-privilege defaults, that ``PROJECT_ID`` is not an alias of
    ``GOOGLE_CLOUD_PROJECT``, and that ``TWITTER_CONSUMER_KEY`` and
    ``TWITTER_CONSUMER_SECRET`` remain undeclared.

Isolation
---------
``Settings`` is a ``BaseSettings`` subclass, so a field's value comes from the
process environment and from the ``.env`` file named by
``Settings.Config.env_file`` before it falls back to its declared default. Any
assertion about a *default* is therefore made against a ``Settings`` built by
:func:`_construct_settings`, which unsets the names under test and disables the
``.env`` source, so neither an exported variable nor a developer's local
``.env`` can decide the outcome. The values read from the shared singleton are
covered by :func:`test_singleton_fields_are_not_shadowed_by_environment`.

This module imports ``app.core.config`` and nothing else from ``app``. Shared
setup — environment seeding for the eight required fields, the Google
credential neutraliser and the socket guard — comes from
``backend/tests/conftest.py``.
"""

import os

import pytest
from pydantic import ValidationError

import app.core.config as config_module
from app.core.config import Settings

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# The contract this suite pins.  Every literal below is read from
# ``app/core/config.py``; none is recomputed from the model.
# --------------------------------------------------------------------------- #

#: The eight fields ``Settings`` declares without a default.
#: ``NOTION_API_KEY`` is declared ``Optional[str] = None`` and is not one of
#: them; :func:`test_settings_omits_notion_api_key` and
#: :func:`test_required_field_set_is_exactly_the_declared_eight` hold that
#: line.
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
#: ``NOTION_API_KEY`` is covered by
#: :func:`test_notion_api_key_default_is_none`, which asserts identity with
#: ``None``.
SINGLETON_FIELD_DEFAULTS = (
    ("PROJECT_NAME", "Twitter Bot"),
    ("API_V1_STR", "/api/v1"),
    ("ACCESS_TOKEN_EXPIRE_MINUTES", 30),
    ("FIRESTORE_COLLECTION_TWEETS", "tweets"),
    ("FIRESTORE_COLLECTION_USERS", "users"),
    ("FIRESTORE_COLLECTION_RESPONSES", "responses"),
)

#: Every field whose value this suite reads from ``config_module.settings``.
SINGLETON_ASSERTED_FIELD_NAMES = tuple(
    [name for name, _ in SINGLETON_FIELD_DEFAULTS]
    + [
        "POPULARITY_THRESHOLD",
        "DOUBT_RATING_THRESHOLD",
        "NOTION_API_KEY",
    ]
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

#: The four fields declared so the application object can be constructed under
#: test, paired with the least-privilege default each carries.
TESTABILITY_FIELD_DEFAULTS = (
    ("ALLOWED_ORIGINS", []),
    ("ALGORITHM", "HS256"),
    ("PROJECT_ID", ""),
    ("TWITTER_TRACK_KEYWORDS", []),
)

#: Names of the fields in :data:`TESTABILITY_FIELD_DEFAULTS`.
TESTABILITY_FIELD_NAMES = tuple(name for name, _ in TESTABILITY_FIELD_DEFAULTS)

#: Read by ``app/services/twitter_service.py`` and
#: ``app/tasks/tweet_processor.py``, declared by ``Settings`` nowhere.  The two
#: suites covering those modules supply them with ``monkeypatch``.
UNDECLARED_CONSUMER_FIELD_NAMES = (
    "TWITTER_CONSUMER_KEY",
    "TWITTER_CONSUMER_SECRET",
)


# --------------------------------------------------------------------------- #
# Shared helper.  Consumed by the required-field matrix and by every test that
# asserts a declared default.  The environment isolation lives here and in no
# other place in this module.
# --------------------------------------------------------------------------- #


def _construct_settings(monkeypatch, absent_fields=()):
    """Build a ``Settings`` with ``absent_fields`` unset and no ``.env`` read.

    Each name in ``absent_fields`` is removed from the process environment
    through ``monkeypatch``, which restores the previous value when the test
    ends, so no test mutates ``os.environ`` itself and no test can leak a
    change into another. ``_env_file=None`` overrides
    ``Settings.Config.env_file`` for this construction, so a ``.env`` on disk
    contributes nothing.

    Returns the constructed ``Settings``. Propagates ``ValidationError`` when a
    required field is left with no value, which is what the required-field
    matrix asserts.
    """
    for field_name in absent_fields:
        monkeypatch.delenv(field_name, raising=False)
    return Settings(_env_file=None)


# --------------------------------------------------------------------------- #
# Declared constants.
# --------------------------------------------------------------------------- #


def test_popularity_threshold_default():
    """``POPULARITY_THRESHOLD`` is 100 on the shared settings singleton.

    ``TweetStreamListener.on_status`` compares
    ``retweet_count + favorite_count`` against this field and returns early
    when the sum is lower, so this value is the oracle the tweet-processor
    suite parametrises its 99 / 100 / 101 matrix around.
    """
    assert (
        config_module.settings.POPULARITY_THRESHOLD
        == POPULARITY_THRESHOLD_DEFAULT
    )


def test_doubt_rating_threshold_default():
    """``DOUBT_RATING_THRESHOLD`` is 0.7 on the shared settings singleton.

    Asserted as a configuration constant only. No production module reads this
    field, so no gate anywhere compares a doubt rating against it; the constant
    is the whole of the implemented behaviour.
    """
    assert (
        config_module.settings.DOUBT_RATING_THRESHOLD
        == DOUBT_RATING_THRESHOLD_DEFAULT
    )


@pytest.mark.parametrize(
    ("field_name", "expected_default"),
    SINGLETON_FIELD_DEFAULTS,
    ids=[name for name, _ in SINGLETON_FIELD_DEFAULTS],
)
def test_settings_default_on_singleton(field_name, expected_default):
    """``field_name`` resolves to its declared default on the singleton.

    These are the values every other backend module sees, because each reads
    them from ``app.core.config.settings`` or from a ``Settings()`` of its own.
    """
    assert getattr(config_module.settings, field_name) == expected_default


def test_notion_api_key_default_is_none():
    """``NOTION_API_KEY`` is ``None`` on the shared settings singleton.

    Asserted with ``is`` rather than ``==`` so an empty string or any other
    falsy value cannot satisfy it.
    """
    assert config_module.settings.NOTION_API_KEY is None


def test_singleton_fields_are_not_shadowed_by_environment():
    """No environment variable supplies a value for a singleton-asserted field.

    ``Settings`` resolves each field from the process environment before
    falling back to its declared default, so a variable named after one of
    these fields would decide the value that
    :func:`test_settings_default_on_singleton`,
    :func:`test_popularity_threshold_default`,
    :func:`test_doubt_rating_threshold_default` and
    :func:`test_notion_api_key_default_is_none` read. This asserts the
    precondition those tests depend on.
    """
    shadowed = sorted(
        name for name in SINGLETON_ASSERTED_FIELD_NAMES if name in os.environ
    )

    assert shadowed == []


# --------------------------------------------------------------------------- #
# The nested ``Settings.Config``.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("attribute_name", "expected_value"),
    CONFIG_ATTRIBUTE_EXPECTATIONS,
    ids=[name for name, _ in CONFIG_ATTRIBUTE_EXPECTATIONS],
)
def test_settings_config_attribute(attribute_name, expected_value):
    """``Settings.Config`` declares ``attribute_name`` as ``expected_value``.

    ``Config`` is a plain nested class rather than a pydantic field, so class
    access resolves here where it raises for every declared field.
    """
    assert getattr(Settings.Config, attribute_name) == expected_value


def test_settings_config_case_sensitive():
    """``Settings.Config.case_sensitive`` is ``True``.

    Asserted with ``is`` because the flag governs whether environment lookups
    match a field name exactly, and only the boolean satisfies the contract.
    """
    assert Settings.Config.case_sensitive is True


# --------------------------------------------------------------------------- #
# Required fields.  One parametrised case per field, so each case reports
# independently.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field_name", REQUIRED_FIELD_NAMES)
def test_settings_requires_field(monkeypatch, field_name):
    """Omitting ``field_name`` makes ``Settings()`` raise ``ValidationError``.

    The raised error is asserted to name ``field_name`` and to carry pydantic
    v1's missing-value error type, so the case cannot pass because some
    *other* field was unset or because a supplied value failed coercion.
    """
    with pytest.raises(ValidationError) as raised:
        _construct_settings(monkeypatch, absent_fields=(field_name,))

    reported = [
        (error["loc"], error["type"]) for error in raised.value.errors()
    ]

    assert ((field_name,), MISSING_FIELD_ERROR_TYPE) in reported


def test_settings_omits_notion_api_key(monkeypatch):
    """``Settings()`` constructs with ``NOTION_API_KEY`` absent, yielding None.

    ``NOTION_API_KEY`` is declared ``Optional[str] = None``, so it is not one
    of the fields in :data:`REQUIRED_FIELD_NAMES`.
    """
    settings = _construct_settings(
        monkeypatch, absent_fields=("NOTION_API_KEY",)
    )

    assert settings.NOTION_API_KEY is None


def test_required_field_set_is_exactly_the_declared_eight():
    """``Settings`` declares exactly the eight fields in
    :data:`REQUIRED_FIELD_NAMES` without a default.

    Comparing the whole set rather than checking membership one name at a time
    fails both if a required field is dropped and if a ninth is introduced.
    """
    required_fields = {
        name
        for name, field in Settings.__fields__.items()
        if field.required
    }

    assert required_fields == set(REQUIRED_FIELD_NAMES)


# --------------------------------------------------------------------------- #
# Class access versus instance access.
# --------------------------------------------------------------------------- #


def test_class_access_google_cloud_project_raises_attribute_error():
    """Class access to ``GOOGLE_CLOUD_PROJECT`` raises ``AttributeError``.

    Class access, not instance access: the name resolves normally on
    ``config_module.settings``.

    pydantic v1 moves declared fields out of the class namespace into
    ``Settings.__fields__``, so the attribute does not exist on ``Settings``
    itself even though it resolves on an instance.

    ``app/db/bigquery.py`` performs exactly this class-level read twice — once
    in ``get_bq_client`` and once in the ``table_id`` f-string of
    ``insert_tweet_analytics`` — which is why ``get_bq_client``, ``run_query``
    and ``insert_tweet_analytics`` are unreachable until a test substitutes the
    name. Declaring further instance fields on ``Settings`` does not change it.
    """
    assert "GOOGLE_CLOUD_PROJECT" in Settings.__fields__
    assert config_module.settings.GOOGLE_CLOUD_PROJECT

    with pytest.raises(AttributeError):
        getattr(Settings, "GOOGLE_CLOUD_PROJECT")


def test_class_access_defaulted_field_raises_attribute_error():
    """Class access raises for a field that declares a default as well.

    ``POPULARITY_THRESHOLD`` is declared ``= 100`` and reading it off the class
    still raises, which shows the behaviour belongs to every pydantic v1 field
    rather than only to the ones declared without a default.
    """
    assert (
        Settings.__fields__["POPULARITY_THRESHOLD"].default
        == POPULARITY_THRESHOLD_DEFAULT
    )

    with pytest.raises(AttributeError):
        getattr(Settings, "POPULARITY_THRESHOLD")


# --------------------------------------------------------------------------- #
# Fields declared so the application object can be constructed under test.
#
# ``configure_cors`` reads ``ALLOWED_ORIGINS``, ``create_access_token`` reads
# ``ALGORITHM``, ``firestore.get_db`` reads ``PROJECT_ID`` and both stream
# starters read ``TWITTER_TRACK_KEYWORDS``.  Each assertion below runs against
# a ``Settings`` built with all four names unset, so it observes the declared
# default rather than whatever the surrounding environment exports.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("field_name", "expected_default"),
    TESTABILITY_FIELD_DEFAULTS,
    ids=TESTABILITY_FIELD_NAMES,
)
def test_testability_field_default(monkeypatch, field_name, expected_default):
    """``field_name`` falls back to its least-privilege declared default.

    ``ALLOWED_ORIGINS`` and ``TWITTER_TRACK_KEYWORDS`` default to the empty
    list rather than to a wildcard or a keyword set, ``ALGORITHM`` to
    ``"HS256"`` and ``PROJECT_ID`` to the empty string. The empty-list defaults
    are asserted by equality, so a wildcard entry cannot satisfy them.
    """
    settings = _construct_settings(
        monkeypatch, absent_fields=TESTABILITY_FIELD_NAMES
    )

    assert getattr(settings, field_name) == expected_default


def test_project_id_is_not_an_alias_of_google_cloud_project():
    """``PROJECT_ID`` and ``GOOGLE_CLOUD_PROJECT`` are independent fields.

    ``PROJECT_ID`` is declared with an empty-string default while
    ``GOOGLE_CLOUD_PROJECT`` is declared without a default, so the two never
    share a value by construction. Asserted on the declared defaults, which no
    environment can shadow.
    """
    assert Settings.__fields__["PROJECT_ID"].default == ""
    assert Settings.__fields__["GOOGLE_CLOUD_PROJECT"].required is True
    assert Settings.__fields__["GOOGLE_CLOUD_PROJECT"].default is None


def test_project_id_does_not_resolve_to_google_cloud_project(monkeypatch):
    """A defaulted ``PROJECT_ID`` differs from a populated
    ``GOOGLE_CLOUD_PROJECT``.

    With ``PROJECT_ID`` unset the field falls back to the empty string while
    ``GOOGLE_CLOUD_PROJECT`` still carries the value seeded for the suite, so
    the two resolve differently on the same instance.
    """
    settings = _construct_settings(
        monkeypatch, absent_fields=TESTABILITY_FIELD_NAMES
    )

    assert settings.GOOGLE_CLOUD_PROJECT
    assert settings.PROJECT_ID != settings.GOOGLE_CLOUD_PROJECT


@pytest.mark.parametrize("field_name", TESTABILITY_FIELD_NAMES)
def test_testability_field_is_declared(field_name):
    """``field_name`` is a declared ``Settings`` field, not a stray attribute.

    Membership in ``Settings.__fields__`` is what makes the name resolvable on
    an instance and overridable from the environment.
    """
    assert field_name in Settings.__fields__


@pytest.mark.parametrize("field_name", UNDECLARED_CONSUMER_FIELD_NAMES)
def test_consumer_field_is_not_declared(field_name):
    """``field_name`` is read by production code but declared by ``Settings``
    nowhere.

    ``start_twitter_stream`` and ``start_tweet_stream`` both read this name, so
    each raises ``AttributeError`` on the settings instance unless a test
    supplies it. The suites covering those modules do so with ``monkeypatch``.
    """
    assert field_name not in Settings.__fields__

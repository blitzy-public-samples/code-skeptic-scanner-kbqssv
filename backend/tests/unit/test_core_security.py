"""Unit suite for ``app/core/security.py``.

Covers the module's four public names -- ``pwd_context``,
``create_access_token``, ``verify_password`` and ``get_password_hash`` --
and the module-scope ``settings`` instance the token signer reads.

Current behaviour captured as divergence
----------------------------------------
``verify_password`` **raises** ``passlib.exc.UnknownHashError`` instead of
returning ``False`` when the stored value is not a hash passlib can
identify.

Signing algorithm
-----------------
``app/core/security.py`` line 18 hands ``settings.ALGORITHM`` to
``jwt.encode``, so that field decides the header of every token this suite
mints and the algorithm ``jwt.decode`` has to be told to accept.
``Settings`` resolves the field from the process environment before the
``.env`` file and before its declared value, so
``backend/tests/conftest.py`` assigns ``ALGORITHM`` at its own module scope,
before ``app.core.security`` is imported. :data:`SIGNING_ALGORITHM` is that
pinned value, :func:`test_module_settings_signing_algorithm_is_hs256` asserts
the subject agrees with it, and no assertion here depends on the surrounding
machine leaving the variable unset.

Shared infrastructure
---------------------
Every expiry assertion runs under the ``frozen_clock`` fixture published by
``backend/tests/conftest.py``, which pins the clock to
``2024-01-01 00:00:00`` UTC.  That module is also the sole installer of the
``builtins.Optional`` shim without which the subject cannot be imported at
all, and of the autouse credential neutraliser and socket guard.  No clock,
shim or guard is established here, and no test in this module reaches a
network boundary.

Isolation
---------
``app/core/security.py`` line 18 reads ``settings.SECRET_KEY`` and
``settings.ALGORITHM`` off the module-scope instance it builds at line 7, and a
``BaseSettings`` field resolves from the environment and from ``.env`` before
its declared default.  Every token test therefore runs under
:func:`token_settings`, which replaces ``app.core.security.settings`` with a
stand-in carrying an explicit key and algorithm, and :func:`_decode_claims`
verifies against that same stand-in.  The signing configuration a token test
observes is consequently fixed by this module, not by the environment the suite
happens to run in.  That ``app/core/config.py`` declares ``HS256`` and that the
singleton resolves to it are asserted by
``backend/tests/unit/test_core_config.py``.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from jose import jwt
from jose.exceptions import ExpiredSignatureError
from passlib.exc import UnknownHashError

import app.core.config as config
import app.core.security as security

pytestmark = pytest.mark.unit

# Oracles.  Every value below is fixed by the frozen instant or by the
# bcrypt configuration.

#: Epoch seconds of ``2024-01-01T00:00:00Z``, the instant ``frozen_clock``
#: pins the clock to.
FROZEN_EPOCH = 1704067200

#: ``exp`` claim of a token minted at :data:`FROZEN_EPOCH` with no
#: ``expires_delta``: the 15-minute default hardcoded at
#: ``app/core/security.py`` line 16 adds 900 seconds to the frozen instant.
DEFAULT_EXPIRY_CLAIM = 1704068100

HARDCODED_LIFETIME_SECONDS = 900

#: Default ``Settings.ACCESS_TOKEN_EXPIRE_MINUTES`` declares, read from
#: ``Settings.__fields__`` rather than from a constructed instance.
CONFIGURED_EXPIRY_MINUTES = 30

#: ``exp`` claim for ``expires_delta=timedelta(minutes=5)`` at the frozen
#: instant.
FIVE_MINUTE_EXPIRY_CLAIM = 1704067500

#: Prefix of a bcrypt ``2b`` hash at cost 12, which is the default cost of a
#: ``CryptContext`` declared with ``schemes=['bcrypt']``.
BCRYPT_2B_COST_12_PREFIX = "$2b$12$"

#: Algorithm the token header must carry and the verifier must require.  Both
#: ``app/core/config.py`` and the parent conftest's environment prologue name
#: this value, so it is fixed for the session; the subject's agreement with it
#: is asserted by :func:`test_module_settings_signing_algorithm_is_hs256`.
SIGNING_ALGORITHM = "HS256"

#: Signing key :func:`token_settings` supplies.  An obvious placeholder; this
#: suite uses no real credential and reads none from the environment.
SIGNING_KEY = "blitzy-test-signing-key-not-a-real-credential"

#: Placeholder password.  This suite uses no real credential.
PLAINTEXT_PASSWORD = "s3cret"

MISMATCHED_PASSWORD = "wrong"

SUBJECT_CLAIM = "u"


@pytest.fixture
def token_settings():
    """Replace ``app.core.security.settings`` for one test.

    ``app/core/security.py`` line 7 builds its own ``Settings`` instance and
    line 18 reads ``SECRET_KEY`` and ``ALGORITHM`` off it at call time, so
    replacing the module attribute is what puts the signing configuration under
    this suite's control.  The stand-in exposes exactly the two fields
    ``create_access_token`` reads.

    Yields the :class:`types.SimpleNamespace` stand-in.  The original instance
    is restored when the test ends.
    """
    stand_in = SimpleNamespace(
        SECRET_KEY=SIGNING_KEY, ALGORITHM=SIGNING_ALGORITHM
    )
    original = security.settings
    security.settings = stand_in
    try:
        yield stand_in
    finally:
        security.settings = original


def _decode_claims(token):
    """Return the verified claims of ``token``.

    The key and algorithm are the ones :func:`token_settings` supplies, so the
    verifier and the signer are configured from the same place and no
    environment value participates.  ``jwt.decode`` verifies the signature and
    the ``exp`` claim together, so it raises ``ExpiredSignatureError`` for a
    token whose lifetime has already elapsed at the current — frozen — instant.
    """
    return jwt.decode(
        token,
        SIGNING_KEY,
        algorithms=[SIGNING_ALGORITHM],
    )


# bcrypt hashing and verification.


def test_get_password_hash_returns_bcrypt_hash():
    """``get_password_hash`` emits a ``2b`` bcrypt hash at cost 12.

    Only the prefix is asserted; bcrypt draws a fresh salt on every call.
    """
    hashed = security.get_password_hash(PLAINTEXT_PASSWORD)

    assert isinstance(hashed, str)
    assert hashed.startswith(BCRYPT_2B_COST_12_PREFIX)


def test_get_password_hash_salts_every_call():
    first = security.get_password_hash(PLAINTEXT_PASSWORD)
    second = security.get_password_hash(PLAINTEXT_PASSWORD)

    assert first != second
    assert security.verify_password(PLAINTEXT_PASSWORD, first) is True
    assert security.verify_password(PLAINTEXT_PASSWORD, second) is True


def test_verify_password_accepts_matching_password():
    hashed = security.get_password_hash(PLAINTEXT_PASSWORD)

    assert security.verify_password(PLAINTEXT_PASSWORD, hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = security.get_password_hash(PLAINTEXT_PASSWORD)

    assert security.verify_password(MISMATCHED_PASSWORD, hashed) is False


def test_pwd_context_configures_bcrypt():
    assert "bcrypt" in security.pwd_context.schemes()


# Verification of a hash passlib cannot identify.


@pytest.mark.parametrize(
    "stored_value",
    ["not-a-hash", ""],
    ids=["unidentifiable", "empty"],
)
def test_verify_password_raises_on_unusable_hash(stored_value):
    """``verify_password`` raises ``UnknownHashError`` instead of ``False``.

    ``verify_password`` delegates straight to ``pwd_context.verify`` and
    catches nothing, so a caller holding an unhashed or empty stored value
    receives an exception rather than a boolean.
    """
    with pytest.raises(UnknownHashError):
        security.verify_password(PLAINTEXT_PASSWORD, stored_value)


# Token minting under a frozen clock.


def test_create_access_token_defaults_to_fifteen_minutes(
    frozen_clock, token_settings
):
    """With no ``expires_delta`` the ``exp`` claim is exactly 1704068100."""
    token = security.create_access_token({"sub": SUBJECT_CLAIM})

    assert _decode_claims(token)["exp"] == DEFAULT_EXPIRY_CLAIM


def test_create_access_token_preserves_payload_claims(
    frozen_clock, token_settings
):
    """The supplied claims survive encoding, under an ``HS256`` header.

    The header algorithm is the observable trace of ``settings.ALGORITHM``,
    which ``app/core/security.py`` line 18 passes to ``jwt.encode``. That field
    is pinned for the session by the parent conftest's environment prologue and
    is asserted independently by
    :func:`test_module_settings_signing_algorithm_is_hs256`.
    """
    token = security.create_access_token({"sub": SUBJECT_CLAIM})

    assert isinstance(token, str)
    assert jwt.get_unverified_header(token)["alg"] == SIGNING_ALGORITHM
    assert _decode_claims(token)["sub"] == SUBJECT_CLAIM


def test_create_access_token_ignores_configured_expiry_minutes(
    frozen_clock, token_settings
):
    """The default lifetime is 900 seconds while the setting asks for 1800.

    ``app/core/security.py`` line 16 hardcodes ``timedelta(minutes=15)`` and
    never reads ``Settings.ACCESS_TOKEN_EXPIRE_MINUTES``, which
    ``app/core/config.py`` line 8 declares as 30.  Both values are asserted
    here, together with the fact that they disagree.

    The configured side is read from ``Settings.__fields__``, which is the
    value the model declares, so the case does not change outcome when the
    environment or a ``.env`` file supplies one.
    """
    token = security.create_access_token({"sub": SUBJECT_CLAIM})

    lifetime_seconds = _decode_claims(token)["exp"] - FROZEN_EPOCH

    assert lifetime_seconds == HARDCODED_LIFETIME_SECONDS
    assert (
        config.Settings.__fields__["ACCESS_TOKEN_EXPIRE_MINUTES"].default
        == CONFIGURED_EXPIRY_MINUTES
    )
    assert lifetime_seconds != CONFIGURED_EXPIRY_MINUTES * 60


def test_create_access_token_honours_explicit_expires_delta(
    frozen_clock, token_settings
):
    """An explicit ``expires_delta`` selects the ``if expires_delta:`` branch.

    Five minutes past the frozen instant is epoch 1704067500.
    """
    token = security.create_access_token(
        {"sub": SUBJECT_CLAIM}, expires_delta=timedelta(minutes=5)
    )

    assert _decode_claims(token)["exp"] == FIVE_MINUTE_EXPIRY_CLAIM


def test_create_access_token_treats_zero_delta_as_falsy(
    frozen_clock, token_settings
):
    """``timedelta(0)`` is falsy, so the 15-minute default applies.

    The branch tests ``if expires_delta:`` rather than ``is not None``, so
    a zero delta lives 900 seconds instead of expiring at once.
    """
    token = security.create_access_token(
        {"sub": SUBJECT_CLAIM}, expires_delta=timedelta(0)
    )

    assert _decode_claims(token)["exp"] == DEFAULT_EXPIRY_CLAIM


def test_create_access_token_negative_delta_produces_expired_token(
    frozen_clock, token_settings
):
    token = security.create_access_token(
        {"sub": SUBJECT_CLAIM}, expires_delta=timedelta(minutes=-1)
    )

    with pytest.raises(ExpiredSignatureError):
        _decode_claims(token)


# Module-scope settings instance.


def test_module_settings_is_an_independent_instance():
    """``app/core/security.py`` builds its own ``Settings`` instance.

    It is not the one ``app/core/config.py`` exports, and both carry the
    same ``SECRET_KEY`` because both read the same environment.
    """
    assert security.settings is not config.settings
    assert security.settings.SECRET_KEY == config.settings.SECRET_KEY


def test_module_settings_signing_algorithm_is_hs256():
    """Both settings instances carry ``HS256`` as ``ALGORITHM``.

    ``app/core/security.py`` line 18 passes ``settings.ALGORITHM`` to
    ``jwt.encode``, so this is the oracle behind every ``jwt.decode`` call in
    this module. The parent conftest pins the environment variable of the same
    name before either instance is constructed, so the value cannot be decided
    by an exported variable or by a ``backend/.env``.
    """
    assert security.settings.ALGORITHM == SIGNING_ALGORITHM
    assert config.settings.ALGORITHM == SIGNING_ALGORITHM

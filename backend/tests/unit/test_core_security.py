"""Unit suite for ``app/core/security.py``.

Covers the module's four public names — ``pwd_context``,
``create_access_token``, ``verify_password`` and ``get_password_hash`` — and
the module-scope ``settings`` instance that the token signer reads.

What this suite asserts
-----------------------
bcrypt configuration
    ``get_password_hash`` emits a ``2b`` bcrypt hash at cost 12, salted
    afresh on every call, and ``verify_password`` returns ``True`` for a
    matching password and ``False`` for a mismatched one.
Verification of an unusable hash
    ``verify_password`` **raises** ``passlib.exc.UnknownHashError`` instead
    of returning ``False`` when the stored value is not a hash passlib can
    identify.  That is current behaviour, and it is asserted as a divergence
    from the design documents' expectation that verification yields a
    boolean for any input.
Token lifetime
    ``create_access_token`` applies a 15-minute lifetime when no
    ``expires_delta`` is supplied and **ignores**
    ``Settings.ACCESS_TOKEN_EXPIRE_MINUTES``, which is 30.  Both values are
    asserted, so that divergence is a recorded fact rather than an
    inference.
Branch selection
    An explicit ``expires_delta`` is honoured, while ``timedelta(0)`` — being
    falsy — selects the 15-minute default instead.
Expired tokens
    A negative ``expires_delta`` produces a token that ``jwt.decode``
    rejects with ``ExpiredSignatureError``.

Shared infrastructure
---------------------
Every expiry assertion runs under the ``frozen_clock`` fixture published by
``backend/tests/conftest.py``, which pins the clock to
``2024-01-01 00:00:00`` UTC.  That module is also the sole installer of the
``builtins.Optional`` shim without which the subject cannot be imported at
all, and of the autouse credential neutraliser and socket guard.  No clock,
shim or guard is established here, and no test in this module reaches a
network boundary.
"""

from datetime import timedelta

import pytest
from jose import jwt
from jose.exceptions import ExpiredSignatureError
from passlib.exc import UnknownHashError

import app.core.config as config
import app.core.security as security

pytestmark = pytest.mark.unit

# --------------------------------------------------------------------------- #
# Oracles.  Every value below is fixed by the frozen instant or by the bcrypt
# configuration.
# --------------------------------------------------------------------------- #

#: Epoch seconds of ``2024-01-01T00:00:00Z``, the instant ``frozen_clock``
#: pins the clock to.
FROZEN_EPOCH = 1704067200

#: ``exp`` claim of a token minted at :data:`FROZEN_EPOCH` with no
#: ``expires_delta``: the 15-minute default hardcoded at
#: ``app/core/security.py`` line 16 adds 900 seconds to the frozen instant.
DEFAULT_EXPIRY_CLAIM = 1704068100

#: Seconds between :data:`FROZEN_EPOCH` and :data:`DEFAULT_EXPIRY_CLAIM`.
HARDCODED_LIFETIME_SECONDS = 900

#: Value ``Settings.ACCESS_TOKEN_EXPIRE_MINUTES`` declares.
CONFIGURED_EXPIRY_MINUTES = 30

#: ``exp`` claim for ``expires_delta=timedelta(minutes=5)`` at the frozen
#: instant.
FIVE_MINUTE_EXPIRY_CLAIM = 1704067500

#: Prefix of a bcrypt ``2b`` hash at cost 12, which is the default cost of a
#: ``CryptContext`` declared with ``schemes=['bcrypt']``.
BCRYPT_2B_COST_12_PREFIX = "$2b$12$"

#: Algorithm the token header must carry and the verifier must require.
SIGNING_ALGORITHM = "HS256"

#: Placeholder password.  This suite uses no real credential, and the signing
#: key is read from the settings instance the parent conftest seeded.
PLAINTEXT_PASSWORD = "s3cret"

#: A password that does not match :data:`PLAINTEXT_PASSWORD`.
MISMATCHED_PASSWORD = "wrong"

#: Subject claim carried through every token round trip.
SUBJECT_CLAIM = "u"


def _decode_claims(token):
    """Return the verified claims of ``token``.

    The signing key is read from the ``app.core.config`` settings instance,
    which ``backend/tests/conftest.py`` seeded from the environment at its
    own module scope.  ``jwt.decode`` verifies the signature and the ``exp``
    claim together, so it raises ``ExpiredSignatureError`` for a token whose
    lifetime has already elapsed at the current — frozen — instant.
    """
    return jwt.decode(
        token,
        config.settings.SECRET_KEY,
        algorithms=[SIGNING_ALGORITHM],
    )


# --------------------------------------------------------------------------- #
# bcrypt hashing and verification.
# --------------------------------------------------------------------------- #


def test_get_password_hash_returns_bcrypt_hash():
    """``get_password_hash`` emits a ``2b`` bcrypt hash at cost 12.

    Only the prefix is asserted: bcrypt draws a fresh salt on every call, so
    the full digest is not reproducible.
    """
    hashed = security.get_password_hash(PLAINTEXT_PASSWORD)

    assert isinstance(hashed, str)
    assert hashed.startswith(BCRYPT_2B_COST_12_PREFIX)


def test_get_password_hash_salts_every_call():
    """Two hashes of one password differ, and both still verify."""
    first = security.get_password_hash(PLAINTEXT_PASSWORD)
    second = security.get_password_hash(PLAINTEXT_PASSWORD)

    assert first != second
    assert security.verify_password(PLAINTEXT_PASSWORD, first) is True
    assert security.verify_password(PLAINTEXT_PASSWORD, second) is True


def test_verify_password_accepts_matching_password():
    """``verify_password`` returns ``True`` for the hashed password."""
    hashed = security.get_password_hash(PLAINTEXT_PASSWORD)

    assert security.verify_password(PLAINTEXT_PASSWORD, hashed) is True


def test_verify_password_rejects_wrong_password():
    """``verify_password`` returns ``False`` for a mismatched password."""
    hashed = security.get_password_hash(PLAINTEXT_PASSWORD)

    assert security.verify_password(MISMATCHED_PASSWORD, hashed) is False


def test_pwd_context_configures_bcrypt():
    """The module-scope ``CryptContext`` is configured for bcrypt."""
    assert "bcrypt" in security.pwd_context.schemes()


# --------------------------------------------------------------------------- #
# Verification of a hash passlib cannot identify.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "stored_value",
    ["not-a-hash", ""],
    ids=["unidentifiable", "empty"],
)
def test_verify_password_raises_on_unusable_hash(stored_value):
    """``verify_password`` raises ``UnknownHashError`` instead of ``False``.

    The stored value here is not a hash passlib can identify, and
    ``app/core/security.py`` line 22 delegates straight to
    ``pwd_context.verify`` and catches nothing, so passlib's
    ``UnknownHashError`` reaches the caller.  This is current behaviour, and
    it diverges from the design documents' expectation that verification
    yields a boolean for any input: a caller holding an unhashed or empty
    stored value receives an exception instead of ``False``.
    """
    with pytest.raises(UnknownHashError):
        security.verify_password(PLAINTEXT_PASSWORD, stored_value)


# --------------------------------------------------------------------------- #
# Token minting under a frozen clock.
# --------------------------------------------------------------------------- #


def test_create_access_token_defaults_to_fifteen_minutes(frozen_clock):
    """With no ``expires_delta`` the ``exp`` claim is exactly 1704068100."""
    token = security.create_access_token({"sub": SUBJECT_CLAIM})

    assert _decode_claims(token)["exp"] == DEFAULT_EXPIRY_CLAIM


def test_create_access_token_preserves_payload_claims(frozen_clock):
    """The supplied claims survive encoding, under an ``HS256`` header.

    The header algorithm is the observable trace of ``settings.ALGORITHM``,
    which ``app/core/security.py`` line 18 passes to ``jwt.encode``.
    """
    token = security.create_access_token({"sub": SUBJECT_CLAIM})

    assert isinstance(token, str)
    assert jwt.get_unverified_header(token)["alg"] == SIGNING_ALGORITHM
    assert _decode_claims(token)["sub"] == SUBJECT_CLAIM


def test_create_access_token_ignores_configured_expiry_minutes(frozen_clock):
    """The default lifetime is 900 seconds while the setting asks for 1800.

    ``app/core/security.py`` line 16 hardcodes ``timedelta(minutes=15)`` and
    never reads ``Settings.ACCESS_TOKEN_EXPIRE_MINUTES``, which
    ``app/core/config.py`` line 8 declares as 30.  Both values are asserted
    here, together with the fact that they disagree.
    """
    token = security.create_access_token({"sub": SUBJECT_CLAIM})

    lifetime_seconds = _decode_claims(token)["exp"] - FROZEN_EPOCH

    assert lifetime_seconds == HARDCODED_LIFETIME_SECONDS
    assert (
        config.settings.ACCESS_TOKEN_EXPIRE_MINUTES
        == CONFIGURED_EXPIRY_MINUTES
    )
    assert lifetime_seconds != CONFIGURED_EXPIRY_MINUTES * 60


def test_create_access_token_honours_explicit_expires_delta(frozen_clock):
    """An explicit ``expires_delta`` selects the ``if expires_delta:`` branch.

    Five minutes past the frozen instant is epoch 1704067500.
    """
    token = security.create_access_token(
        {"sub": SUBJECT_CLAIM}, expires_delta=timedelta(minutes=5)
    )

    assert _decode_claims(token)["exp"] == FIVE_MINUTE_EXPIRY_CLAIM


def test_create_access_token_treats_zero_delta_as_falsy(frozen_clock):
    """``timedelta(0)`` is falsy, so the 15-minute default applies.

    ``app/core/security.py`` line 13 tests ``if expires_delta:`` rather than
    ``if expires_delta is not None:``, so a zero delta takes the ``else``
    branch and the token lives 900 seconds instead of expiring at once.
    """
    token = security.create_access_token(
        {"sub": SUBJECT_CLAIM}, expires_delta=timedelta(0)
    )

    assert _decode_claims(token)["exp"] == DEFAULT_EXPIRY_CLAIM


def test_create_access_token_negative_delta_produces_expired_token(
    frozen_clock,
):
    """A negative ``expires_delta`` yields a token ``jwt.decode`` rejects.

    Encoding and decoding both happen at the frozen instant, so the
    rejection follows from the ``exp`` claim alone.
    """
    token = security.create_access_token(
        {"sub": SUBJECT_CLAIM}, expires_delta=timedelta(minutes=-1)
    )

    with pytest.raises(ExpiredSignatureError):
        _decode_claims(token)


# --------------------------------------------------------------------------- #
# Module-scope settings instance.
# --------------------------------------------------------------------------- #


def test_module_settings_is_an_independent_instance():
    """``app/core/security.py`` line 7 builds its own ``Settings``.

    It is not the instance ``app/core/config.py`` exports, and both carry
    the same ``SECRET_KEY`` because both read the same environment.
    """
    assert security.settings is not config.settings
    assert security.settings.SECRET_KEY == config.settings.SECRET_KEY

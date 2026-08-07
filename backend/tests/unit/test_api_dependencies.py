"""Unit suite for ``app/api/dependencies.py``, the bearer-token dependency.

The subject declares two public names: the module-level
``oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")`` and the coroutine
function ``get_current_user(token)``, whose whole body is one ``try`` block
guarded by a bare ``except Exception as e``.

What this suite asserts
-----------------------
* ``oauth2_scheme`` is an ``OAuth2PasswordBearer`` whose password flow declares
  ``tokenUrl`` as the relative path ``"token"``.
* Every falsy ``verify_token`` result raises ``HTTPException`` with
  ``status_code`` 401 and ``detail`` ``"Could not validate credentials"``.
* The token argument reaches ``verify_token`` unchanged, exactly once.
* A ``verify_token`` that raises any ``Exception`` subclass produces the
  identical ``HTTPException``: the same status and the same detail.
* A truthy ``verify_token`` result is returned unchanged, asserted by identity.
* ``get_current_user`` is a coroutine function.
* ``get_db`` is bound into the module and no code path calls it.
* With no patch applied, the shim the suite imports the module under is
  fail-closed: an arbitrary token is rejected with 401 rather than accepted.

Current behaviour captured as divergence
----------------------------------------
``detail="Invalid token"`` is unobservable to any caller.  It is raised
*inside* the ``try``, and ``HTTPException`` is an ``Exception`` subclass, so
the bare ``except Exception`` catches it and re-raises with the generic
detail.  Both 401 paths are therefore indistinguishable from outside the
function, and the specific message survives only as the implicit
``__context__`` of the exception that is actually raised.

The swallowed failure is discarded silently: ``e`` is bound and never used,
no explicit chaining is performed, and the subject emits no diagnostic
output, so ``__cause__`` is ``None``.

``get_current_user`` is declared ``async`` yet awaits nothing: it calls
``verify_token`` synchronously.

``verify_token``, imported from ``app.core.security`` at line 3, is defined by
no production module; the ``app_module`` fixture in
``backend/tests/conftest.py`` installs the shim that makes the import resolve.
That shim is fail-closed — it raises ``MissingProductionSymbolError`` on every
call — which matters because line 3 binds the object into *this* module's
namespace at import time and ``app.api.dependencies`` is deliberately never
evicted from ``sys.modules``. A permissive stand-in would therefore stay
reachable for the rest of the session and make line 13 return a principal for
any token at all. :func:`test_get_current_user_is_fail_closed_without_a_patch`
asserts the shipped default; every other test supplies its own result through
:func:`mock_verify_token`, which patches the attribute on this module.

``get_db``, imported at line 4, is never used. The declared ``tokenUrl`` names
a ``/token`` endpoint that this application does not implement.

Scope
-----
Every test invokes ``get_current_user`` directly with a token string.
FastAPI's dependency resolution, the HTTP surface and the response a
missing ``Authorization`` header produces belong to
``backend/tests/integration/``.
"""

import importlib
import inspect
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer

pytestmark = pytest.mark.unit

# Oracles.  Every value below is read from the subject module.

SUBJECT_MODULE = "app.api.dependencies"

UNAUTHORIZED_STATUS = 401

GENERIC_401_DETAIL = "Could not validate credentials"

#: Detail from line 12.  Never observable as a raised exception's ``detail``.
UNREACHABLE_401_DETAIL = "Invalid token"

EXPECTED_TOKEN_URL = "token"

#: Argument handed to ``get_current_user``.  ``verify_token`` is replaced by a
#: mock in every test, so the value is never decoded.  It is not a credential
#: and not a well-formed JWT.
THROWAWAY_TOKEN = "blitzy-throwaway-token-not-a-credential"

FALSY_VERIFY_TOKEN_RESULTS = (
    pytest.param(None, id="none"),
    pytest.param(False, id="false"),
    pytest.param({}, id="empty-dict"),
    pytest.param("", id="empty-string"),
    pytest.param(0, id="zero"),
)

VERIFY_TOKEN_FAILURES = (
    pytest.param(Exception, "boom", id="exception"),
    pytest.param(ValueError, "malformed token", id="valueerror"),
)


# Fixtures.  Shared infrastructure comes from backend/tests/conftest.py;
# the two below are specific to this module.


@pytest.fixture
def api_dependencies_module(app_module):
    """Return the imported ``app.api.dependencies`` module.

    The subject imports ``verify_token`` from ``app.core.security``, which
    no production module defines, so importing it without the shim raises
    ``ImportError``.  ``app_module`` is requested for the three shims it
    installs, which stay in place for the whole test.
    """
    return importlib.import_module(SUBJECT_MODULE)


@pytest.fixture
def mock_verify_token(api_dependencies_module):
    """Replace ``app.api.dependencies.verify_token`` for one test.

    The patch target is the attribute on the *subject* module, which bound
    the name with ``from app.core.security import verify_token``, and not
    ``app.core.security.verify_token``.

    Yields the :class:`unittest.mock.MagicMock` installed in its place; the
    patch is undone when the test ends.
    """
    with patch.object(
        api_dependencies_module, "verify_token", MagicMock(name="verify_token")
    ) as mock:
        yield mock


# oauth2_scheme contract.


def test_oauth2_scheme_is_oauth2_password_bearer(api_dependencies_module):
    assert isinstance(
        api_dependencies_module.oauth2_scheme, OAuth2PasswordBearer
    )


def test_oauth2_scheme_declares_token_url(api_dependencies_module):
    """The scheme's password flow declares ``tokenUrl`` as ``"token"``.

    fastapi 0.95.2 exposes the value at
    ``oauth2_scheme.model.flows.password.tokenUrl``, and the password flow
    is the only one populated.
    """
    flows = api_dependencies_module.oauth2_scheme.model.flows

    assert flows.password is not None
    assert flows.password.tokenUrl == EXPECTED_TOKEN_URL


# Path 1 -- verify_token returns a falsy value.


@pytest.mark.parametrize("falsy_user", FALSY_VERIFY_TOKEN_RESULTS)
async def test_get_current_user_raises_401_when_verify_token_returns_falsy(
    api_dependencies_module, mock_verify_token, falsy_user
):
    """A falsy ``verify_token`` result raises 401 with the generic detail.

    ``None``, ``False``, ``{}``, ``""`` and ``0`` all surface
    ``"Could not validate credentials"``, never ``"Invalid token"``.
    """
    mock_verify_token.return_value = falsy_user

    with pytest.raises(HTTPException) as excinfo:
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    assert excinfo.value.status_code == UNAUTHORIZED_STATUS
    assert excinfo.value.detail == GENERIC_401_DETAIL


async def test_get_current_user_calls_verify_token_once_with_the_token(
    api_dependencies_module, mock_verify_token
):
    mock_verify_token.return_value = None

    with pytest.raises(HTTPException):
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    mock_verify_token.assert_called_once_with(THROWAWAY_TOKEN)


# Path 2 -- verify_token raises.


@pytest.mark.parametrize("failure_type, message", VERIFY_TOKEN_FAILURES)
async def test_get_current_user_raises_401_when_verify_token_raises(
    api_dependencies_module, mock_verify_token, failure_type, message
):
    mock_verify_token.side_effect = failure_type(message)

    with pytest.raises(HTTPException) as excinfo:
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    assert excinfo.value.status_code == UNAUTHORIZED_STATUS
    assert excinfo.value.detail == GENERIC_401_DETAIL


async def test_get_current_user_discards_the_original_exception(
    api_dependencies_module, mock_verify_token
):
    """The failure from ``verify_token`` is replaced, not propagated.

    The caller receives a new ``HTTPException`` carrying only the status
    and the generic detail.  ``__cause__`` is ``None`` because no explicit
    chaining is performed, so the implicit ``__context__`` is the only
    remaining trace of the original.
    """
    original = ValueError("malformed token")
    mock_verify_token.side_effect = original

    with pytest.raises(HTTPException) as excinfo:
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    raised = excinfo.value
    assert type(raised) is HTTPException
    assert raised is not original
    assert raised.status_code == UNAUTHORIZED_STATUS
    assert raised.detail == GENERIC_401_DETAIL
    assert raised.__cause__ is None
    assert raised.__context__ is original


# The unreachable detail.


async def test_get_current_user_never_surfaces_invalid_token_detail(
    api_dependencies_module, mock_verify_token
):
    """``detail="Invalid token"`` is never the detail a caller observes.

    A falsy result is the only input that reaches that raise.  It happens
    inside the ``try``, the bare ``except Exception`` catches its own
    ``HTTPException``, and the replacement carries the generic detail, so
    the specific one is demoted to the implicit ``__context__``.
    """
    mock_verify_token.return_value = None

    with pytest.raises(HTTPException) as excinfo:
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    raised = excinfo.value
    assert raised.detail != UNREACHABLE_401_DETAIL
    assert raised.detail == GENERIC_401_DETAIL

    swallowed = raised.__context__
    assert isinstance(swallowed, HTTPException)
    assert swallowed.status_code == UNAUTHORIZED_STATUS
    assert swallowed.detail == UNREACHABLE_401_DETAIL


# Happy path and remaining contract.


async def test_get_current_user_returns_the_verified_user_unchanged(
    api_dependencies_module, mock_verify_token
):
    verified_user = object()
    mock_verify_token.return_value = verified_user

    returned = await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    assert returned is verified_user


def test_get_current_user_is_a_coroutine_function(api_dependencies_module):
    """``get_current_user`` is a coroutine function that awaits nothing."""
    assert inspect.iscoroutinefunction(
        api_dependencies_module.get_current_user
    )


async def test_get_current_user_is_fail_closed_without_a_patch(
    api_dependencies_module,
):
    """An unpatched ``verify_token`` rejects the token instead of accepting it.

    This test deliberately does not request :func:`mock_verify_token`, so
    ``app.api.dependencies.verify_token`` is whatever the ``app_module`` fixture
    left bound — the fail-closed sentinel from ``backend/tests/conftest.py``.
    Calling it raises, the bare ``except Exception`` on line 14 catches that, and
    line 15 answers 401.

    The assertion is the harness's trust boundary rather than production
    behaviour: production defines no ``verify_token`` at all, so there is no
    real implementation for this call to reach. What is asserted is that the
    stand-in cannot be mistaken for one — a truthy stand-in would make line 13
    return a mock principal for an arbitrary bearer token, and every suite that
    imports this module afterwards would inherit that.
    """
    with pytest.raises(HTTPException) as excinfo:
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    assert excinfo.value.status_code == UNAUTHORIZED_STATUS
    assert excinfo.value.detail == GENERIC_401_DETAIL

    swallowed = excinfo.value.__context__
    assert type(swallowed).__name__ == "MissingProductionSymbolError"
    assert "verify_token" in str(swallowed)


async def test_dependencies_module_imports_get_db_without_calling_it(
    api_dependencies_module, mock_verify_token
):
    """``get_db`` is bound into the module and no code path calls it.

    A successful ``get_current_user`` leaves the replacement untouched.
    """
    assert hasattr(api_dependencies_module, "get_db")
    mock_verify_token.return_value = object()

    with patch.object(
        api_dependencies_module, "get_db", MagicMock(name="get_db")
    ) as mock_get_db:
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    mock_get_db.assert_not_called()

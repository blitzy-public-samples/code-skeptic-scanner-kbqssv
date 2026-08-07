"""Unit suite for ``app/api/dependencies.py``, the bearer-token dependency.

Subject
-------
``backend/app/api/dependencies.py`` is fifteen lines and declares two public
names: the module-level security scheme
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

Current behaviour captured as divergence
----------------------------------------
``detail="Invalid token"`` is unobservable to any caller. Line 12 raises it
*inside* the ``try`` opened on line 9; ``HTTPException`` is an ``Exception``
subclass, so the bare ``except Exception as e`` on line 14 catches it and line
15 re-raises with the generic detail. Line 12 therefore executes — a coverage
report marks it covered — while the message it carries reaches nobody: it
survives only as the implicit ``__context__`` of the exception that is
actually raised. Both 401 paths are indistinguishable from outside the
function. The branch is a documented ceiling, not a coverage gap.

The swallowed failure is discarded silently. Line 14 binds ``e`` and never
uses it, line 15 performs no explicit chaining, and there is no diagnostic
output anywhere in ``backend/app`` — so ``__cause__`` is ``None`` and the only
trace of the original is the implicit ``__context__`` the interpreter sets.

``get_current_user`` is declared ``async`` yet awaits nothing: it calls
``verify_token`` synchronously.

``verify_token``, imported from ``app.core.security`` at line 3, is defined by
no production module; the ``app_module`` fixture in
``backend/tests/conftest.py`` installs the shim that makes the import resolve.
``get_db``, imported at line 4, is never used. The declared ``tokenUrl`` names
a ``/token`` endpoint that this application does not implement.

Scope
-----
Every test invokes ``get_current_user`` directly with a token string. FastAPI's
dependency resolution, the HTTP surface and the response a missing
``Authorization`` header produces belong to ``backend/tests/integration/``.
"""

import importlib
import inspect
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer

pytestmark = pytest.mark.unit

# --------------------------------------------------------------------------- #
# Oracles.  Every value below is read from app/api/dependencies.py.
# --------------------------------------------------------------------------- #

#: Import path of the subject.  ``app.*`` is the suite's single import root,
#: established by ``pythonpath = .`` in ``backend/pytest.ini``.
SUBJECT_MODULE = "app.api.dependencies"

#: Status code both 401 paths carry (lines 12 and 15).
UNAUTHORIZED_STATUS = 401

#: Detail every caller observes, from line 15.
GENERIC_401_DETAIL = "Could not validate credentials"

#: Detail from line 12.  Never observable as a raised exception's ``detail``.
UNREACHABLE_401_DETAIL = "Invalid token"

#: ``tokenUrl`` passed to ``OAuth2PasswordBearer`` on line 6.
EXPECTED_TOKEN_URL = "token"

#: Argument handed to ``get_current_user``.  ``verify_token`` is replaced by a
#: mock in every test, so the value is never decoded.  It is not a credential
#: and not a well-formed JWT.
THROWAWAY_TOKEN = "blitzy-throwaway-token-not-a-credential"

#: Falsy results that drive line 11 into line 12.
FALSY_VERIFY_TOKEN_RESULTS = (
    pytest.param(None, id="none"),
    pytest.param(False, id="false"),
    pytest.param({}, id="empty-dict"),
    pytest.param("", id="empty-string"),
    pytest.param(0, id="zero"),
)

#: ``(type, message)`` pairs for the exception ``verify_token`` raises.  Each
#: test constructs its own instance from the pair.
VERIFY_TOKEN_FAILURES = (
    pytest.param(Exception, "boom", id="exception"),
    pytest.param(ValueError, "malformed token", id="valueerror"),
)


# --------------------------------------------------------------------------- #
# Fixtures.  Shared infrastructure comes from backend/tests/conftest.py; the
# two below are specific to this module.
# --------------------------------------------------------------------------- #


@pytest.fixture
def api_dependencies_module(app_module):
    """Return the imported ``app.api.dependencies`` module.

    ``app/api/dependencies.py`` line 3 executes
    ``from app.core.security import verify_token``, and no production module
    defines that symbol, so importing the subject without the shim raises
    ``ImportError: cannot import name 'verify_token'``. ``app_module`` is
    requested for the three shims it installs — ``verify_token``,
    ``TwitterService`` and ``LLMService`` — which stay in place for the whole
    test; ``backend/tests/conftest.py`` publishes it as the fixture the suite
    covering this module consumes.

    The parent ``conftest.py`` installs ``builtins.Optional`` at its own module
    scope, which is what makes ``app.core.security`` importable at all.
    """
    return importlib.import_module(SUBJECT_MODULE)


@pytest.fixture
def mock_verify_token(api_dependencies_module):
    """Replace ``app.api.dependencies.verify_token`` for one test.

    The patch target is the attribute on the *subject* module, which line 3
    binds with ``from app.core.security import verify_token``, and not
    ``app.core.security.verify_token``.

    Yields the :class:`unittest.mock.MagicMock` installed in its place. A test
    sets ``return_value`` or ``side_effect`` on it; the patch is undone when
    the test ends, so no case observes another case's configuration.
    """
    with patch.object(
        api_dependencies_module, "verify_token", MagicMock(name="verify_token")
    ) as mock:
        yield mock


# --------------------------------------------------------------------------- #
# oauth2_scheme contract.
# --------------------------------------------------------------------------- #


def test_oauth2_scheme_is_oauth2_password_bearer(api_dependencies_module):
    """``oauth2_scheme`` is an ``OAuth2PasswordBearer`` instance."""
    assert isinstance(
        api_dependencies_module.oauth2_scheme, OAuth2PasswordBearer
    )


def test_oauth2_scheme_declares_token_url(api_dependencies_module):
    """The scheme's password flow declares ``tokenUrl`` as ``"token"``.

    fastapi 0.95.2 exposes the value at
    ``oauth2_scheme.model.flows.password.tokenUrl``, and the password flow is
    the only one populated. The path is relative and names a ``/token``
    endpoint that this application does not implement.
    """
    flows = api_dependencies_module.oauth2_scheme.model.flows

    assert flows.password is not None
    assert flows.password.tokenUrl == EXPECTED_TOKEN_URL


# --------------------------------------------------------------------------- #
# Path 1 — verify_token returns a falsy value.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("falsy_user", FALSY_VERIFY_TOKEN_RESULTS)
async def test_get_current_user_raises_401_when_verify_token_returns_falsy(
    api_dependencies_module, mock_verify_token, falsy_user
):
    """A falsy ``verify_token`` result raises 401 with the generic detail.

    ``None``, ``False``, ``{}``, ``""`` and ``0`` all fail the truth test on
    line 11 and all surface ``"Could not validate credentials"``, never
    ``"Invalid token"``.
    """
    mock_verify_token.return_value = falsy_user

    with pytest.raises(HTTPException) as excinfo:
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    assert excinfo.value.status_code == UNAUTHORIZED_STATUS
    assert excinfo.value.detail == GENERIC_401_DETAIL


async def test_get_current_user_calls_verify_token_once_with_the_token(
    api_dependencies_module, mock_verify_token
):
    """The token argument reaches ``verify_token`` unchanged, exactly once."""
    mock_verify_token.return_value = None

    with pytest.raises(HTTPException):
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    mock_verify_token.assert_called_once_with(THROWAWAY_TOKEN)


# --------------------------------------------------------------------------- #
# Path 2 — verify_token raises.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("failure_type, message", VERIFY_TOKEN_FAILURES)
async def test_get_current_user_raises_401_when_verify_token_raises(
    api_dependencies_module, mock_verify_token, failure_type, message
):
    """A raising ``verify_token`` produces the same 401 as a falsy result.

    ``except Exception`` on line 14 catches the base ``Exception`` and any
    subclass of it, so the outcome does not depend on the failure's type.
    """
    mock_verify_token.side_effect = failure_type(message)

    with pytest.raises(HTTPException) as excinfo:
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    assert excinfo.value.status_code == UNAUTHORIZED_STATUS
    assert excinfo.value.detail == GENERIC_401_DETAIL


async def test_get_current_user_discards_the_original_exception(
    api_dependencies_module, mock_verify_token
):
    """The failure from ``verify_token`` is replaced, not propagated.

    What a caller receives is a new ``HTTPException`` carrying only the status
    and the generic detail: the raised object is not the original, and
    ``__cause__`` is ``None`` because line 15 performs no explicit chaining.
    The interpreter's implicit ``__context__`` holds the original, which is the
    sole remaining trace of it — line 14 binds ``e`` and never uses it, and the
    module produces no diagnostic output.
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


# --------------------------------------------------------------------------- #
# The unreachable detail on line 12.
# --------------------------------------------------------------------------- #


async def test_get_current_user_never_surfaces_invalid_token_detail(
    api_dependencies_module, mock_verify_token
):
    """``detail="Invalid token"`` is never the detail a caller observes.

    The falsy result is the only input that executes line 12. Line 12 raises
    inside the ``try`` opened on line 9, the bare ``except Exception`` on line
    14 catches its own ``HTTPException``, and line 15 replaces it. The
    ``"Invalid token"`` exception is therefore demoted to the implicit
    ``__context__`` of the exception that reaches the caller, whose detail is
    always the generic one. Line 12 is covered by this test and its effect is
    still unobservable.
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


# --------------------------------------------------------------------------- #
# Happy path and remaining contract.
# --------------------------------------------------------------------------- #


async def test_get_current_user_returns_the_verified_user_unchanged(
    api_dependencies_module, mock_verify_token
):
    """A truthy ``verify_token`` result is returned by identity.

    Line 13 hands back exactly the object line 10 produced: it is neither
    copied, wrapped nor coerced.
    """
    verified_user = object()
    mock_verify_token.return_value = verified_user

    returned = await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    assert returned is verified_user


def test_get_current_user_is_a_coroutine_function(api_dependencies_module):
    """``get_current_user`` is a coroutine function.

    It is declared ``async`` and awaits nothing: line 10 calls
    ``verify_token`` synchronously.
    """
    assert inspect.iscoroutinefunction(
        api_dependencies_module.get_current_user
    )


async def test_dependencies_module_imports_get_db_without_calling_it(
    api_dependencies_module, mock_verify_token
):
    """``get_db`` is bound into the module and no code path calls it.

    Line 4 imports it from ``app.db.firestore``; the only function in the
    module never references it. A successful ``get_current_user`` leaves the
    replacement untouched.
    """
    assert hasattr(api_dependencies_module, "get_db")
    mock_verify_token.return_value = object()

    with patch.object(
        api_dependencies_module, "get_db", MagicMock(name="get_db")
    ) as mock_get_db:
        await api_dependencies_module.get_current_user(THROWAWAY_TOKEN)

    mock_get_db.assert_not_called()

"""Dependency-closure gate for the backend test environment.

Subject
-------
``backend/requirements-dev.txt`` is the only Python manifest in the repository
and every one of its entries is an exact ``==`` pin. This module asserts that
the interpreter running the suite has *those* versions installed, so a run can
never report green while exercising a different dependency graph from the one
the repository declares.

Relationship to ``pip check``
----------------------------
``pip check`` verifies that installed distributions satisfy one another's
declared ranges; it does not compare an installed version against a manifest
pin, because a pin in a requirements file is not a runtime constraint on
anything already present. The two checks are therefore complementary, and a
stale environment passes ``pip check``. Reasoning for enforcing the comparison
here: ``docs/testing/DECISION-LOG.md`` §10, rows D100 and D101.

Pins whose exact version is security-relevant, so a mismatch is not cosmetic:

* ``python-jose[cryptography]==3.5.0`` — ``app/core/security.py`` line 2 imports
  ``jwt`` from it, so it is the JWT implementation the whole token surface runs
  on. 3.5.0 rather than the 3.3.0 the AAP named: 3.3.0 is affected by
  CVE-2024-33663 (algorithm and key confusion) and CVE-2024-33664
  (compressed-JWE decompression bomb), and a version below 3.4.0 reaching an
  environment is exactly what this gate exists to catch.
* ``bcrypt==4.0.1`` — ``passlib`` 1.7.4 cannot drive the 5.x line, so a silent
  upgrade breaks every password assertion rather than merely changing it.

What is asserted
----------------
For every ``name==version`` line in the manifest: the distribution is installed,
and its installed version string equals the pinned one exactly. Extras are part
of the requirement syntax rather than of the distribution name, so
``python-jose[cryptography]==3.5.0`` is checked as ``python-jose`` at ``3.5.0``;
whether the extra's own dependency is present is what ``pip check`` covers.

Scope
-----
This module reads a text file and the installed-distribution metadata. It
imports no ``app`` module, opens no socket and needs no fixture.
"""

import importlib.metadata as importlib_metadata
import os
import re

import pytest

pytestmark = pytest.mark.unit

# --------------------------------------------------------------------------- #
# Manifest location and parsing.
# --------------------------------------------------------------------------- #

#: ``backend/requirements-dev.txt``, resolved from this file rather than from
#: the working directory, so the gate is invoked identically however pytest is
#: started.
REQUIREMENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "requirements-dev.txt",
)

#: One exact pin. Group 1 is the distribution name, group 2 the optional extras
#: bracket, group 3 the version. A comment or blank line matches nothing.
PIN_EXPRESSION = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[(?P<extras>[^\]]*)\])?"
    r"==(?P<version>[^\s#]+)\s*$"
)


def _parse_pins(requirements_text):
    """Return ``[(name, version), ...]`` for every ``==`` pin in the manifest.

    Comment lines, blank lines and any requirement expressed with an operator
    other than ``==`` are skipped: this gate asserts exact pins and makes no
    claim about a range.
    """
    pins = []
    for line in requirements_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = PIN_EXPRESSION.match(stripped)
        if match is not None:
            pins.append((match.group("name"), match.group("version")))
    return pins


with open(REQUIREMENTS_PATH, encoding="utf-8") as _requirements_file:
    #: Every exact pin the manifest declares, in file order.
    PINNED_DISTRIBUTIONS = tuple(_parse_pins(_requirements_file.read()))

del _requirements_file


# --------------------------------------------------------------------------- #
# The gate.
# --------------------------------------------------------------------------- #


def test_manifest_declares_pins():
    """The manifest parsed to a non-empty set of exact pins.

    Guards the parametrised case below against silently degenerating into zero
    cases if the manifest were emptied, renamed or rewritten with ranges.
    """
    assert PINNED_DISTRIBUTIONS != ()


@pytest.mark.parametrize(
    ("distribution", "pinned_version"),
    PINNED_DISTRIBUTIONS,
    ids=["{0}=={1}".format(name, version) for name, version in PINNED_DISTRIBUTIONS],
)
def test_installed_version_matches_manifest(distribution, pinned_version):
    """``distribution`` is installed at exactly the version the manifest pins.

    A mismatch means the suite is exercising a dependency graph the repository
    does not declare. Rebuild the environment with
    ``pip install -r backend/requirements-dev.txt`` before trusting a result.
    """
    try:
        installed_version = importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover - env
        pytest.fail(
            "{0} is pinned to {1} in backend/requirements-dev.txt and is not "
            "installed. Run: pip install -r backend/requirements-dev.txt".format(
                distribution, pinned_version
            )
        )

    assert installed_version == pinned_version, (
        "{0} is pinned to {1} in backend/requirements-dev.txt but {2} is "
        "installed. Run: pip install -r backend/requirements-dev.txt".format(
            distribution, pinned_version, installed_version
        )
    )

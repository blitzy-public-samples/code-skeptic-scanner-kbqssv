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

* ``python-jose[cryptography]==3.3.0`` — ``app/core/security.py`` line 2 imports
  ``jwt`` from it, so it is the JWT implementation the whole token surface runs
  on. 3.3.0 is the version AAP §0.6.1 declares, and it is affected by
  CVE-2024-33663 (algorithm and key confusion) and CVE-2024-33664
  (compressed-JWE decompression bomb), both fixed in 3.4.0. Neither is reachable
  from any test here: the suite only encodes and decodes HS256 with an explicit
  key, so no JWE is decrypted and no OpenSSH ECDSA key is loaded. The exposure is
  escalated as an open item rather than closed by raising a pin the plan fixed,
  and this gate is what makes the version the suite actually ran against
  verifiable rather than assumed.
* ``bcrypt==4.0.1`` — ``passlib`` 1.7.4 cannot drive the 5.x line, so a silent
  upgrade breaks every password assertion rather than merely changing it.

What is asserted
----------------
* Every active line of the manifest — every line that is neither blank nor a
  comment — matches the exact-pin grammar. A requirement expressed with any other
  operator, an unpinned bare name, or a pip option line fails a case rather than
  being skipped, so a dependency cannot leave this gate by ceasing to be a pin.
* The number of pins parsed equals the number of active lines, and no
  distribution is pinned twice under any spelling of its name.
* For every pin: the distribution is installed, and its installed version string
  equals the pinned one exactly.

Extras are part of the requirement syntax rather than of the distribution name,
so ``python-jose[cryptography]==3.3.0`` is checked as ``python-jose`` at
``3.3.0``; whether the extra's own dependency is present is what ``pip check``
covers.

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
#:
#: The version class excludes every PEP 440 operator character, so ``===`` -
#: arbitrary equality, which is not an exact pin - cannot be read as ``==``
#: followed by a version of ``=8.4.2``, and a comma-separated specifier set
#: cannot be read as a pin either.
PIN_EXPRESSION = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[(?P<extras>[^\]]*)\])?"
    r"==(?P<version>[^\s#<>=!~,]+)\s*$"
)


def _active_requirement_lines(requirements_text):
    """Return every line of ``requirements_text`` that declares a requirement.

    A line is active when it is neither empty nor a whole-line comment. Each is
    returned stripped, so a caller compares against the grammar rather than
    against whitespace.
    """
    return tuple(
        stripped
        for stripped in (line.strip() for line in requirements_text.splitlines())
        if stripped and not stripped.startswith("#")
    )


def _normalized_distribution_name(name):
    """Return ``name`` in the PEP 503 normalized form.

    ``Python-JOSE``, ``python_jose`` and ``python.jose`` are one distribution, so
    the uniqueness case compares this form rather than the literal spelling.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _partition_requirements(requirements_text):
    """Split the manifest's active lines into parsed pins and everything else.

    Returns ``(pins, nonconforming)`` where ``pins`` is
    ``[(name, version), ...]`` in file order and ``nonconforming`` is every active
    line the exact-pin grammar rejects. Nothing is discarded: the two lists
    together account for every active line, which is what lets the cases below
    assert that the partition is exhaustive.
    """
    pins = []
    nonconforming = []
    for stripped in _active_requirement_lines(requirements_text):
        match = PIN_EXPRESSION.match(stripped)
        if match is None:
            nonconforming.append(stripped)
        else:
            pins.append((match.group("name"), match.group("version")))
    return pins, nonconforming


with open(REQUIREMENTS_PATH, encoding="utf-8") as _requirements_file:
    _REQUIREMENTS_TEXT = _requirements_file.read()

del _requirements_file

#: Every line of the manifest that declares a requirement, in file order.
ACTIVE_REQUIREMENT_LINES = _active_requirement_lines(_REQUIREMENTS_TEXT)

_PINS, _NONCONFORMING = _partition_requirements(_REQUIREMENTS_TEXT)

#: Every exact pin the manifest declares, in file order.
PINNED_DISTRIBUTIONS = tuple(_PINS)

#: Every active line the exact-pin grammar rejects. Must be empty.
NONCONFORMING_REQUIREMENT_LINES = tuple(_NONCONFORMING)

#: Requirement forms this gate must reject, one per shape pip accepts and this
#: manifest must not use. Each is a whole active line.
NONCONFORMING_EXAMPLES = (
    pytest.param("pytest>=8.4.2", id="lower-bound"),
    pytest.param("pytest<=8.4.2", id="upper-bound"),
    pytest.param("pytest>8.0,<9.0", id="range"),
    pytest.param("pytest~=8.4.2", id="compatible-release"),
    pytest.param("pytest!=8.4.1", id="exclusion"),
    pytest.param("pytest===8.4.2", id="arbitrary-equality"),
    pytest.param("pytest", id="bare-name"),
    pytest.param("python-jose[cryptography]>=3.3.0", id="extras-with-range"),
    pytest.param("-r constraints.txt", id="include-option"),
    pytest.param("--index-url https://example.invalid/simple", id="index-option"),
    pytest.param("-e ./local-package", id="editable-install"),
    pytest.param(
        "https://example.invalid/pytest-8.4.2-py3-none-any.whl", id="direct-url"
    ),
)


# --------------------------------------------------------------------------- #
# The gate.
# --------------------------------------------------------------------------- #


def test_manifest_declares_pins():
    """The manifest parsed to a non-empty set of exact pins.

    Guards the parametrised case below against silently degenerating into zero
    cases if the manifest were emptied, renamed or rewritten with ranges.
    """
    assert PINNED_DISTRIBUTIONS != ()


def test_manifest_declares_active_requirement_lines():
    """The manifest carries at least one line that declares a requirement.

    Separate from the case above so an emptied manifest is distinguishable from
    one whose lines all failed the grammar.
    """
    assert ACTIVE_REQUIREMENT_LINES != ()


def test_every_active_line_is_an_exact_pin():
    """No active line escapes the gate by ceasing to be an exact ``==`` pin.

    The parametrised installed-version case below has one case per pin, so a
    requirement rewritten as a range would otherwise simply lose its case and the
    gate would stay green with one fewer assertion.
    """
    assert NONCONFORMING_REQUIREMENT_LINES == ()


def test_the_pin_count_equals_the_active_line_count():
    """Every active line produced exactly one pin - the partition is exhaustive."""
    assert len(PINNED_DISTRIBUTIONS) == len(ACTIVE_REQUIREMENT_LINES)


def test_no_distribution_is_pinned_twice():
    """Each distribution appears once, compared in PEP 503 normalized form.

    Two pins of one distribution would make the last one win at install time
    while both were asserted, so one of the two cases could only ever fail.
    """
    normalized = [
        _normalized_distribution_name(name) for name, _ in PINNED_DISTRIBUTIONS
    ]

    duplicates = sorted({name for name in normalized if normalized.count(name) > 1})

    assert duplicates == []


@pytest.mark.parametrize("line", NONCONFORMING_EXAMPLES)
def test_a_requirement_that_is_not_an_exact_pin_is_reported(line):
    """The grammar rejects every non-pin form, rather than skipping it.

    Drives :func:`_partition_requirements` with a synthetic one-line manifest, so
    the rejection is asserted on the same code path the module-scope partition
    uses. This is the negative half of :func:`test_every_active_line_is_an_exact_pin`:
    without it, that case would also pass if the grammar accepted everything.
    """
    pins, nonconforming = _partition_requirements(line)

    assert pins == []
    assert nonconforming == [line]


def test_a_comment_or_blank_line_is_not_an_active_line():
    """Comments and blank lines are excluded before the grammar is applied."""
    text = "\n".join(
        ["", "   ", "# a comment", "\t# an indented comment", "pytest==8.4.2"]
    )

    pins, nonconforming = _partition_requirements(text)

    assert _active_requirement_lines(text) == ("pytest==8.4.2",)
    assert pins == [("pytest", "8.4.2")]
    assert nonconforming == []


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

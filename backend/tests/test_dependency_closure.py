"""Dependency-closure gate for the backend test environment.

Subject
-------
``backend/requirements-dev.txt`` is the only Python manifest in the repository
and every one of its entries is an exact ``==`` pin. This module asserts that
the interpreter running the suite has *those* versions installed, so a run can
never report green while exercising a different dependency graph from the one
the repository declares.

The gate has two directions, and both are necessary:

**Manifest → environment.** Every pin the manifest declares is installed at
exactly that version.

**Use → manifest.** Every third-party distribution the backend test
infrastructure *reaches for* is declared by the manifest. This direction is what
catches a package the suite depends on directly while the manifest leaves it to
arrive transitively — a dependency the repository uses without declaring, which
the first direction cannot see because it only ever looks at lines that are
already there.

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
  on. The pin sits above CVE-2024-33663 (algorithm and key confusion) and
  CVE-2024-33664 (compressed-JWE decompression bomb), which affect 3.3.0 and are
  fixed in 3.4.0; this gate is what makes the version the suite actually ran
  against verifiable rather than assumed.
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
* Every module the test tree reaches for — whether through an ``import``
  statement or through a module path named as a string, which is how the egress
  guard in ``conftest.py`` reaches ``grpc``, ``grpc.aio`` and ``grpc._channel`` —
  is either first-party, or part of the standard library, or provided by a
  distribution the manifest pins. A module that is none of those three fails a
  case naming it and the distribution that provides it.

Extras are part of the requirement syntax rather than of the distribution name,
so ``python-jose[cryptography]==3.5.0`` is checked as ``python-jose`` at
``3.5.0``; whether the extra's own dependency is present is what ``pip check``
covers.

Scope
-----
This module reads the manifest, parses the test tree with :mod:`ast`, reads the
guard's own target tables out of the already-imported ``conftest``, and reads
installed-distribution metadata. It imports no ``app`` module, opens no socket
and needs no fixture. Parsing a file is not executing it, so nothing here runs
test code.
"""

import ast
import importlib.metadata as importlib_metadata
import importlib.util
import os
import re
import sys
import sysconfig

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

#: Every pinned distribution, in PEP 503 normalized form, for membership tests.
PINNED_DISTRIBUTION_NAMES = frozenset(
    _normalized_distribution_name(name) for name, _ in PINNED_DISTRIBUTIONS
)

# --------------------------------------------------------------------------- #
# Use -> manifest closure: what the test tree reaches for.
# --------------------------------------------------------------------------- #

#: ``backend/tests`` - the only tree this direction of the gate reads.
TESTS_ROOT = os.path.dirname(os.path.abspath(__file__))

#: Top-level names that are this repository's own code rather than a dependency.
FIRST_PARTY_ROOTS = frozenset({"app", "tests", "conftest"})

#: Callables whose first positional argument, when it is a string literal, names a
#: module path rather than a value. ``patch("app.db.firestore.get_db")`` and the
#: guard's own ``self._add("grpc", "secure_channel")`` are both of this shape, and
#: neither is visible to an import scan.
MODULE_NAMING_CALLEES = frozenset({"patch", "import_module", "_add"})

#: Attributes of :mod:`conftest` holding ``(module, attribute)`` guard targets.
#: Each is a table of module paths the guard patches by name.
GUARD_TARGET_TABLES = (
    "GRPC_CHANNEL_FACTORIES",
    "DNS_RESOLVERS",
    "OUT_OF_BAND_CONNECTORS",
    "METHOD_CONNECTORS",
    "CHILD_PROCESS_FACTORIES",
)


def _dotted_prefixes(dotted, depth=2):
    """Return ``dotted`` truncated to each length from ``depth`` down to 1.

    ``"google.api_core.grpc_helpers"`` yields ``("google.api_core", "google")``.
    A provider lookup tries these in order, so the most specific distribution that
    claims the path wins and a namespace package still resolves to something.
    """
    parts = [part for part in dotted.split(".") if part]
    if not parts:
        return ()
    return tuple(".".join(parts[:length]) for length in range(min(depth, len(parts)), 0, -1))


def _python_files(root):
    """Yield every ``.py`` file under ``root``, deepest-first order irrelevant."""
    for directory, _subdirectories, filenames in os.walk(root):
        if "__pycache__" in directory:
            continue
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield os.path.join(directory, filename)


def _imported_module_paths(tree):
    """Return every absolute module path an ``import`` statement in ``tree`` names.

    Relative imports carry no distribution, so ``ImportFrom`` nodes with a
    non-zero ``level`` are excluded. ``import a.b.c`` contributes ``a.b.c`` and
    ``from a.b import c`` contributes ``a.b``; truncation to a provider key
    happens in :func:`_dotted_prefixes`.
    """
    paths = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                paths.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                paths.add(node.module)
    return paths


def _string_named_module_paths(tree):
    """Return module paths named as string literals in ``tree``.

    Covers the calls in :data:`MODULE_NAMING_CALLEES`, whose first positional
    argument is a dotted target rather than a value. This is the only way a
    dependency reached purely by name - the gRPC channel factories the egress
    guard patches - becomes visible to a static reading.
    """
    paths = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        callee = node.func
        name = getattr(callee, "attr", None) or getattr(callee, "id", None)
        if name not in MODULE_NAMING_CALLEES:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            candidate = first.value
            if candidate and re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", candidate):
                paths.add(candidate)
    return paths


def _guard_target_module_paths():
    """Return module paths the ``conftest`` guard tables name.

    ``conftest`` is already imported by pytest before any test module is read, so
    this reads its constants out of :data:`sys.modules` rather than importing
    anything for a second time. A table that a future edit renames simply stops
    contributing, which is why the string-literal scan above covers the same
    ground independently.
    """
    module = sys.modules.get("tests.conftest") or sys.modules.get("conftest")
    if module is None:  # pragma: no cover - conftest is always loaded first
        return set()

    paths = set()
    for table_name in GUARD_TARGET_TABLES:
        for entry in getattr(module, table_name, ()):
            if isinstance(entry, tuple) and entry and isinstance(entry[0], str):
                paths.add(entry[0])
    return paths


def _module_paths_reached_by_the_test_tree():
    """Every module path the test tree reaches, from all three discovery routes."""
    paths = set()
    for path in _python_files(TESTS_ROOT):
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        paths |= _imported_module_paths(tree)
        paths |= _string_named_module_paths(tree)
    paths |= _guard_target_module_paths()
    return paths


def _module_path_providers():
    """Map a dotted module path to the normalized distributions providing it.

    Built from installed metadata rather than from a hand-written table, so a
    renamed or re-vendored package cannot silently fall out of the mapping.
    ``top_level.txt`` is preferred where a distribution ships one; otherwise the
    recorded file list supplies the same information. Keys are held at one and two
    dotted levels, which is what lets ``google.api_core`` resolve to
    ``google-api-core`` rather than to whichever distribution happens to own the
    ``google`` namespace directory.
    """
    providers = {}

    def claim(module_path, distribution):
        providers.setdefault(module_path, set()).add(distribution)

    for distribution in importlib_metadata.distributions():
        raw_name = distribution.metadata["Name"]
        if not raw_name:
            continue
        name = _normalized_distribution_name(raw_name)

        declared = distribution.read_text("top_level.txt") or ""
        for line in declared.splitlines():
            top_level = line.strip()
            if top_level and top_level.isidentifier():
                claim(top_level, name)

        for recorded in distribution.files or ():
            parts = [part for part in str(recorded).replace("\\", "/").split("/") if part]
            if not parts or parts[0] in ("..", "__pycache__"):
                continue
            head = parts[0]
            if head.endswith((".dist-info", ".egg-info", ".data")):
                continue
            if len(parts) == 1:
                if head.endswith(".py") and head[:-3].isidentifier():
                    claim(head[:-3], name)
                continue
            if not head.isidentifier():
                continue
            claim(head, name)
            second = parts[1]
            if second.endswith(".py"):
                second = second[:-3]
            if second.isidentifier():
                claim("{0}.{1}".format(head, second), name)

    return providers


#: Dotted module path -> normalized distributions that provide it.
MODULE_PATH_PROVIDERS = _module_path_providers()

#: Directories the running interpreter serves the standard library from. On POSIX
#: ``site-packages`` sits *inside* the stdlib directory, so a path is stdlib only
#: when it is under one of these and under none of :data:`SITE_PACKAGES_PATHS`.
STDLIB_PATHS = frozenset(
    os.path.realpath(path)
    for path in (sysconfig.get_paths().get("stdlib"), sysconfig.get_paths().get("platstdlib"))
    if path
)

#: Directories installed distributions live in.
SITE_PACKAGES_PATHS = frozenset(
    os.path.realpath(path)
    for path in (sysconfig.get_paths().get("purelib"), sysconfig.get_paths().get("platlib"))
    if path
)


def _is_within(candidate, roots):
    """Whether ``candidate`` is one of ``roots`` or sits underneath one."""
    real = os.path.realpath(candidate)
    return any(real == root or real.startswith(root + os.sep) for root in roots)


def _resolution_locations(module_path):
    """Return the filesystem locations ``module_path`` resolves to, or ``None``.

    ``None`` means the import system cannot resolve it at all. An empty tuple
    means it resolves to something with no location - a built-in or frozen module.
    """
    if module_path.split(".")[0] in sys.builtin_module_names:
        return ()
    try:
        spec = importlib.util.find_spec(module_path)
    except (ImportError, AttributeError, ValueError):
        return None
    if spec is None:
        return None

    locations = []
    if spec.origin and spec.origin not in ("built-in", "frozen"):
        locations.append(spec.origin)
    if spec.submodule_search_locations:
        locations.extend(str(location) for location in spec.submodule_search_locations)
    return tuple(locations)


def classify_module_path(module_path):
    """Classify ``module_path`` as ``first-party``, ``stdlib``, ``third-party`` or ``unresolvable``.

    ``third-party`` is decided by installed metadata first and by location second,
    so a distribution that ships no ``top_level.txt`` and no recorded file list is
    still classified from where the import system finds it.
    """
    if module_path.split(".")[0] in FIRST_PARTY_ROOTS:
        return "first-party"

    for prefix in _dotted_prefixes(module_path):
        if prefix in MODULE_PATH_PROVIDERS:
            return "third-party"

    locations = _resolution_locations(module_path)
    if locations is None:
        return "unresolvable"
    if not locations:
        return "stdlib"
    if any(_is_within(location, SITE_PACKAGES_PATHS) for location in locations):
        return "third-party"
    if any(_is_within(location, STDLIB_PATHS) for location in locations):
        return "stdlib"
    return "third-party"


def providers_for(module_path):
    """Return the distributions providing ``module_path``, most specific first."""
    for prefix in _dotted_prefixes(module_path):
        providers = MODULE_PATH_PROVIDERS.get(prefix)
        if providers:
            return frozenset(providers)
    return frozenset()


#: Every module path the test tree reaches, in a stable order.
MODULE_PATHS_REACHED = tuple(sorted(_module_paths_reached_by_the_test_tree()))

#: The third-party subset - one parametrised closure case each.
THIRD_PARTY_MODULE_PATHS = tuple(
    module_path
    for module_path in MODULE_PATHS_REACHED
    if classify_module_path(module_path) == "third-party"
)

#: Module paths the import system cannot resolve at all. Must be empty: a path the
#: test tree names and nothing provides is a broken reference, not a dependency.
UNRESOLVABLE_MODULE_PATHS = tuple(
    module_path
    for module_path in MODULE_PATHS_REACHED
    if classify_module_path(module_path) == "unresolvable"
)

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


# --------------------------------------------------------------------------- #
# The second direction: everything the test tree reaches is declared.
# --------------------------------------------------------------------------- #


def test_the_test_tree_reaches_third_party_modules():
    """Discovery found third-party module paths at all.

    Guards the parametrised closure case below against degenerating into zero
    cases if the scan were broken, the tree moved, or every classification came
    back first-party.
    """
    assert THIRD_PARTY_MODULE_PATHS != ()


def test_the_grpc_targets_the_egress_guard_patches_are_discovered():
    """The three gRPC module paths reached only by name are in the scanned set.

    ``conftest.py`` patches ``grpc``, ``grpc.aio`` and ``grpc._channel`` through
    string module names, so an import scan alone reports the suite as having no
    gRPC dependency at all. This case pins the discovery route that sees them, so
    the closure case below cannot lose its gRPC coverage silently.
    """
    for module_path in ("grpc", "grpc.aio", "grpc._channel"):
        assert module_path in MODULE_PATHS_REACHED


def test_every_module_path_reached_resolves():
    """No module path the test tree names is unresolvable in this interpreter."""
    assert UNRESOLVABLE_MODULE_PATHS == ()


@pytest.mark.parametrize("module_path", THIRD_PARTY_MODULE_PATHS)
def test_a_module_the_tree_reaches_is_provided_by_a_pinned_distribution(module_path):
    """``module_path`` comes from a distribution ``requirements-dev.txt`` pins.

    This is the direction ``pip check`` and the manifest-to-environment cases
    cannot cover: a package the test infrastructure reaches for directly while the
    manifest leaves it to arrive transitively through something else. Such a
    dependency works until the intermediate package drops it, at which point the
    failure names the intermediate rather than the real dependant.
    """
    providers = providers_for(module_path)
    declared = providers & PINNED_DISTRIBUTION_NAMES

    assert declared, (
        "backend/tests reaches {0}, which is provided by {1}, and "
        "backend/requirements-dev.txt pins none of them. Declare an exact pin for "
        "the one it depends on, or stop reaching for the module.".format(
            module_path, ", ".join(sorted(providers)) or "no installed distribution"
        )
    )


def test_classification_separates_the_three_kinds_of_module():
    """:func:`classify_module_path` answers each kind from a known example.

    Drives the classifier directly so the parametrised case above cannot pass by
    classifying everything as first-party and iterating over nothing.
    """
    assert classify_module_path("app.core.config") == "first-party"
    assert classify_module_path("tests.factories") == "first-party"
    assert classify_module_path("os.path") == "stdlib"
    assert classify_module_path("json") == "stdlib"
    assert classify_module_path("sys") == "stdlib"
    assert classify_module_path("grpc") == "third-party"
    assert classify_module_path("pytest") == "third-party"
    assert classify_module_path("no_such_distribution_anywhere") == "unresolvable"


def test_a_string_named_module_is_discovered_from_a_patch_call():
    """The string-literal scan finds a module named in a ``patch`` or ``_add`` call."""
    source = "\n".join(
        [
            "patch('grpc.aio.secure_channel')",
            "self._add('grpc._channel', 'Channel')",
            "importlib.import_module('google.api_core.grpc_helpers')",
            "patch.object(module, 'attribute')",
            "some_other_call('not.a.module.target')",
        ]
    )

    found = _string_named_module_paths(ast.parse(source))

    assert found == {
        "grpc.aio.secure_channel",
        "grpc._channel",
        "google.api_core.grpc_helpers",
    }


def test_an_import_statement_is_discovered_and_a_relative_one_is_not():
    """Absolute imports contribute a module path; relative imports carry none."""
    source = "\n".join(
        [
            "import grpc",
            "import google.api_core.grpc_helpers",
            "from freezegun import freeze_time",
            "from . import factories",
            "from .factories import make_tweet",
        ]
    )

    found = _imported_module_paths(ast.parse(source))

    assert found == {"grpc", "google.api_core.grpc_helpers", "freezegun"}


def test_provider_lookup_prefers_the_most_specific_distribution():
    """A two-level path resolves ahead of the namespace root it sits in.

    ``google`` is claimed by every ``google-*`` distribution installed, so a
    lookup that stopped at the root would report a dependency as declared whenever
    any one of them was pinned. ``google.api_core`` is claimed by
    ``google-api-core`` alone.
    """
    assert _dotted_prefixes("google.api_core.grpc_helpers") == ("google.api_core", "google")
    assert providers_for("google.api_core.grpc_helpers") == frozenset({"google-api-core"})
    assert providers_for("grpc._channel") == frozenset({"grpcio"})

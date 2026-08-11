"""Contract tests for the counts and path claims the Rule 1 and Rule 2 documents make.

Subject
-------
``docs/testing/TRACEABILITY-MATRIX.md`` and ``docs/testing/DASHBOARD-TEMPLATE.md``.
Both documents make claims that are arithmetic rather than editorial -- how many
``.gitignore`` patterns exist, how many manifest lines are exact pins, how many
rows the artifact census carries, which layer labels the extractor emits -- and a
claim of that kind drifts the moment the thing it counts changes. Nothing else in
this repository re-derives them, so before this module a stale count read exactly
like a current one.

What is asserted
----------------
Only claims with a mechanical oracle:

Counts stated in prose against the artifact they count
    The ``.gitignore`` pattern census in section F row F39, the manifest pin census
    in section H row H1, the section F row count in the header prose and in the
    completeness table, and the ``<section>`` count the deck census states.

Rule 4's numeric limits on the executive deck
    Per slide: at most forty body words and four bullets on a content slide, three
    bullets on the closing slide, one non-text visual on every slide. The word count
    is taken on the strictest reading available -- headings counted, hyphenated words
    split, raw Mermaid source counted -- so a slide that passes here passes on every
    looser reading. The measured vector is also matched against the figure the
    decision log states, which is what stops the log drifting away from the file.

Path ownership, in both directions
    Every file of the delivered suite is named by at least one section F row, and
    every path a section F row names resolves to a file that exists.

Producer and template agreement
    The layer labels ``docs/testing/DASHBOARD-TEMPLATE.md`` documents are exactly
    the labels ``docs/testing/dashboard-extract.py`` emits.

One provenance hash across every document
    The commit a figure was measured against is quoted in several files; they must
    quote the same one.

Cross-references to a wholly superseded decision
    ``DECISION-LOG.md`` appends rather than rewrites, so a downstream document can
    cite a row whose ruling has since been reversed and read as current. Where the
    log declares a row superseded **in whole**, a document citing it must cite its
    superseder as well. Rows superseded only in part are excluded by construction:
    citing the half that still stands is correct, and 21 such citations exist.

A marker a document invites the reader to grep for
    ``SECURITY-GAPS.md`` describes annotations that live in the backend manifest.
    A quoted marker that the manifest does not carry defeats the check the row
    invites, so each is required to be present verbatim.

What is not asserted
--------------------
Anything requiring a subprocess. The conftest guards refuse a child process while a
test runs, so this module reads the filesystem and never invokes ``git``. The
change-set figures in the completeness table that only ``git diff`` can produce are
therefore checked for internal arithmetic consistency and against the on-disk
census, not re-derived from the object store.

@see docs/testing/TRACEABILITY-MATRIX.md - the document under test.
@see docs/testing/DASHBOARD-TEMPLATE.md - the second document under test.
@see blitzy-deck/executive-summary.html - the deck whose Rule 4 limits are asserted.
@see docs/testing/DECISION-LOG.md - rows D336 and D337.
"""

import io
import json
import os
import re

import pytest

pytestmark = pytest.mark.unit


#: Repository root, two levels above ``backend/tests``.
REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MATRIX_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "TRACEABILITY-MATRIX.md")
DASHBOARD_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "DASHBOARD-TEMPLATE.md")
DECISION_LOG_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "DECISION-LOG.md")
SECURITY_GAPS_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "SECURITY-GAPS.md")
EXTRACTOR_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "dashboard-extract.py")
GITIGNORE_PATH = os.path.join(REPOSITORY_ROOT, ".gitignore")
MANIFEST_PATH = os.path.join(REPOSITORY_ROOT, "backend", "requirements-dev.txt")
DECK_PATH = os.path.join(REPOSITORY_ROOT, "blitzy-deck", "executive-summary.html")

#: Documents that cite decision rows and are read as current rather than as history.
#: ``DECISION-LOG.md`` itself is excluded: it *is* the history, and a row is expected to
#: name the row it replaced.
CITING_DOCUMENTS = (
    os.path.join("docs", "testing", "TRACEABILITY-MATRIX.md"),
    os.path.join("docs", "testing", "DASHBOARD-TEMPLATE.md"),
    os.path.join("docs", "testing", "SECURITY-GAPS.md"),
    "README.md",
    os.path.join("backend", "tests", "README.md"),
    os.path.join("frontend", "TESTING.md"),
    os.path.join("e2e", "README.md"),
    os.path.join("blitzy-deck", "executive-summary.html"),
)

#: Rows the log declares superseded **in whole**, mapped to the rows that replace them.
#: Twelve are re-derived from the log below; the last three are stated only in the
#: supersession index, so they are listed here and each is asserted to be stated there.
WHOLE_ROW_SUPERSESSIONS = {
    "D7": ("D103", "D136"),
    "D8": ("D170",),
    "D43": ("D126",),
    "D116": ("D136",),
    "D137": ("D170",),
    "D163": ("D196",),
    "D166": ("D171",),
    "D167": ("D172",),
    "D192": ("D208",),
    "D234": ("D235",),
    "D266": ("D308",),
    "D339": ("D292",),
    "D270": ("D292",),
    "D271": ("D293",),
    "D273": ("D285",),
}

#: Documents that publish the backend suite's size. ``DECISION-LOG.md`` is excluded: its rows
#: state the figure each earlier checkpoint measured, and D354 freezes those as history.
COUNT_PUBLISHING_DOCUMENTS = (
    "README.md",
    os.path.join("backend", "tests", "README.md"),
    os.path.join("docs", "testing", "DASHBOARD-TEMPLATE.md"),
    os.path.join("docs", "testing", "TRACEABILITY-MATRIX.md"),
)

#: Every phrasing a document uses to state how many backend cases the suite collects.
COLLECTED_PATTERNS = (
    r"all (\d{3,5}) tests are collected",
    r"\*\*Current state:\*\* (\d{3,5}) tests collected",
    r"collects all (\d{3,5}) tests",
    r"`(\d{3,5}) tests collected`",
    r"\*\*counts\*\* \u2014 (\d{3,5}) backend cases",
    r'tests="(\d{3,5})">',
    r"Backend \*\*(\d{3,5}) collected",
    r"(\d{3,5}) of \d{3,5} distinct",
)

#: Every phrasing a document uses to state how many of them pass. Each pattern is anchored to
#: a whole-suite statement: a per-suite figure such as the ``tests/unit`` row is a different
#: number and must not be dragged into the comparison.
PASSED_PATTERNS = (
    r"(\d{3,5}) passing, 3 skipped",
    r"\*\*(\d{3,5}) passed / 3 reasoned skips\*\* on the backend",
    r"\| `pytest` \| `(\d{3,5}) passed, 3 skipped` \|",
    r"the same `(\d{3,5}) passed, 3 skipped`",
    r"identical `(\d{3,5}) passed, 3 skipped`",
    r"\*\*(\d{3,5}) passed, 3 skipped, exit 0",
    r"errors, (\d{3,5}) passed, 3 skipped",
    r"\((\d{3,5}) backend, \d+ frontend",
)

#: Documents that publish the *frontend* suite's result. The count-publishing set plus
#: ``frontend/TESTING.md``, which carries the runner's own summary line as a committed
#: transcript and is therefore the witness the rest are held to. That matters because
#: ``frontend/reports/jest-junit.xml`` is gitignored: a check that reads only the artifact
#: passes vacuously in a fresh clone, which is exactly the state a reader restating these
#: figures is least likely to be in.
FRONTEND_RESULT_DOCUMENTS = COUNT_PUBLISHING_DOCUMENTS + (
    os.path.join("frontend", "TESTING.md"),
)

#: Every phrasing a delivered document uses to publish that result, each with the figures its
#: capture groups yield, in order. A phrasing states only some of them, so the readings are
#: compared field by field and a document is never held to a number it makes no claim about.
#: ``tests`` is the root total; ``suites`` the suite total. The first shape is the artifact
#: summary, the second the runner's verbatim summary line, the third the reader-facing prose,
#: the fourth the three-stream sum the deck's headline is built from.
FRONTEND_RESULT_PATTERNS = (
    (r"(\d+) suites passed / (\d+) skipped, (\d+) passed / (\d+) skipped, exit 0",
     ("suites_passed", "suites_skipped", "passed", "skipped")),
    (r"Suites: (\d+) skipped, (\d+) passed, \d+ of (\d+) total\. "
     r"Tests: (\d+) skipped, (\d+) passed, (\d+) total",
     ("suites_skipped", "suites_passed", "suites", "skipped", "passed", "tests")),
    (r"\*\*(\d+) passed / (\d+) reasoned skips across (\d+) suites\*\*",
     ("passed", "skipped", "suites")),
    (r"\(\d{3,5} backend, (\d+) frontend", ("passed",)),
)

#: The retained frontend result stream, when a suite has been run in this working tree. The
#: counterpart of :data:`E2E_JUNIT_PATH` for the layer whose figure QA found contradicted.
FRONTEND_JUNIT_PATH = os.path.join(REPOSITORY_ROOT, "frontend", "reports", "jest-junit.xml")

#: Review findings the log's §40 register puts to an owner, whether to ratify a deviation
#: from the frozen plan's literal text or to record that a scope clause already allows it.
ESCALATED_DEVIATIONS = ("F3", "F4", "F5", "F6", "F12", "F17", "F21")

#: The skips that fire only when a *previous* run's artifact is absent, each with the
#: reason string its own ``pytest.skip`` call carries. They are why a first pass from a
#: fresh clone reports fewer passes and more skips than a warm run: neither test can be
#: evaluated until the artifact it reads exists, and both artifacts are gitignored.
ARTIFACT_CONDITIONAL_SKIPS = (
    (os.path.join("backend", "tests", "test_coverage_gate.py"),
     "backend/coverage.json is written by the gated coverage command"),
    (os.path.join("backend", "tests", "test_docs_contract.py"),
     "e2e/reports/e2e-junit.xml is gitignored and absent in a fresh clone"),
)

#: Documents whose readers run the suite themselves, and would otherwise read the warm
#: figure as the only one. Each has to state the first-pass figure beside it.
FIRST_PASS_DOCUMENTS = ("README.md", os.path.join("backend", "tests", "README.md"))

#: How those documents state the first pass. Deliberately not a phrasing
#: :data:`PASSED_PATTERNS` matches: this is a second, conditional figure, and the
#: one-figure-everywhere check must not read it as a document disagreeing with itself.
FIRST_PASS_PATTERN = r"(\d{3,5}) passed and (\d+) skipped on a first pass"

#: How the root README states what a bare ``pytest`` from the repository root produces.
ROOT_MISUSE_PATTERN = r"\*\*(\d+) failed, (\d{3,5}) passed, (\d+) skipped\*\*"

#: The JWT pin as delivered. A backlog entry describing this change as unattempted is a
#: document contradicting the manifest beside it, which is the failure this pair catches.
DELIVERED_PIN = "python-jose[cryptography]==3.5.0"

#: The two section headings ``backend/requirements-dev.txt`` partitions itself with, in file
#: order. The documents describe the split as "N test-stack distributions and M of the runtime
#: stack", so the partition has to be derived from the file rather than counted by hand: that
#: is what let a manifest of 26 be published as 25 in three places while a fourth said 26.
MANIFEST_SECTIONS = ("# test stack", "# runtime stack the tests exercise")

#: Every phrasing a document uses to publish the manifest's pin census. The first two are the
#: prose form in the two onboarding documents, the third the matrix's section F cell, and the
#: fourth the matrix's section H claim - the only one of the four that was already bound, and
#: the only one that was right.
MANIFEST_CENSUS_PATTERNS = (
    r"exact-pinned throughout: all \*\*(\d+)\*\* active lines are `==`",
    r"fully exact-pinned: all \*\*(\d+)\*\* active lines of",
    r"suite executes against: (\d+) exact pins",
    r"`backend/requirements-dev\.txt` \((\d+) active lines",
)

#: How the root README states the split across those two sections.
MANIFEST_SPLIT_PATTERN = (r"(\d+) test-stack distributions and (\d+) of the runtime stack "
                          r"the tests exercise")

#: Markers ``SECURITY-GAPS.md`` states the backend manifest carries, each required in it.
MANIFEST_MARKERS = (
    "# SECURITY: above CVE-2024-33663 / CVE-2024-33664, fixed in 3.4.0.",
    "python-jose[cryptography]==3.5.0",
)

#: The end-to-end census every document publishes: cases, then spec files. One number in
#: one place, so a document that states a different one is a failure rather than a reading.
E2E_PUBLISHED_TESTS = 31
E2E_PUBLISHED_SPECS = 5

#: Number words the documents spell out in an E2E census claim. The stale value is kept in
#: the map deliberately: a regression to it then fails on its *value* rather than by
#: falling out of the pattern and passing unnoticed.
NUMBER_WORDS = {
    "nineteen": 19, "twenty-one": 21, "thirty-one": 31, "twelve": 12, "eighty-five": 85,
}

#: Parametrisation ids for :data:`CITING_DOCUMENTS`: the relative path, because three of
#: the documents are named ``README.md`` and a basename id would collide.
CITING_DOCUMENT_IDS = [path.replace(os.sep, "/") for path in CITING_DOCUMENTS]

#: Claim shapes that carry the E2E case count. The first is the artifact-shaped form, the
#: second the discovery-listing form; both are what a reader copies into a report.
E2E_NUMERIC_CLAIMS = (
    r'tests="(\d+)" failures="0" skipped="0" errors="0"',
    r"Total: (\d+) tests in (\d+) files",
)

#: Claim shapes that spell the count out in prose.
E2E_WORD_CLAIMS = (
    r"([A-Za-z-]+) browser flows passed",
    r"([A-Za-z-]+) tests across five specs",
)

#: The retained E2E result stream, when a suite has been run in this working tree.
E2E_JUNIT_PATH = os.path.join(REPOSITORY_ROOT, "e2e", "reports", "e2e-junit.xml")

#: The retained E2E discovery listing, the independent witness of how many cases the layer
#: has. ``playwright test --list`` writes it and a *result* run never touches it, so it is
#: what distinguishes a whole-suite stream from a one-spec one.
E2E_LIST_TESTS_PATH = os.path.join(REPOSITORY_ROOT, "e2e", "reports", "list-tests.txt")

#: The line ``playwright test --list`` closes with, and the only line read out of it.
E2E_DISCOVERY_TOTAL = r"Total:\s+(\d+)\s+tests?\s+in\s+(\d+)\s+files?"

#: E2E scripts that can run a subset of the suite or wait on a human, and therefore must
#: never write the canonical result stream. Each pins a reporter override.
PARTIAL_CAPABLE_E2E_SCRIPTS = ("test:spec", "test:debug", "test:headed")

#: The override each of those scripts pins, replacing the configured reporter list.
E2E_REPORTER_OVERRIDE = "--reporter=line"

#: The E2E package manifest, read as text so a script body is asserted as written.
E2E_MANIFEST_PATH = os.path.join(REPOSITORY_ROOT, "e2e", "package.json")

#: The E2E onboarding document, which has to name every command it protects.
E2E_README_PATH = os.path.join(REPOSITORY_ROOT, "e2e", "README.md")

#: Directories whose every file is part of the delivered suite.
SCOPE_DIRECTORIES = (
    os.path.join("backend", "tests"),
    os.path.join("frontend", "src", "test-utils"),
    "e2e",
    os.path.join("docs", "testing"),
    "blitzy-deck",
)

#: Individual files that are part of the delivered suite without their directory being.
SCOPE_FILES = (
    os.path.join("backend", "pytest.ini"),
    os.path.join("backend", "requirements-dev.txt"),
    os.path.join("backend", ".coveragerc"),
    os.path.join("backend", "app", "core", "config.py"),
    os.path.join("backend", "app", "api", "routes", "tweets.py"),
    os.path.join("backend", "app", "api", "routes", "users.py"),
    os.path.join("backend", "app", "api", "routes", "analytics.py"),
    os.path.join("backend", "app", "api", "routes", "config.py"),
    os.path.join("frontend", "jest.config.js"),
    os.path.join("frontend", "jest.transform.extensionless.js"),
    os.path.join("frontend", "package.json"),
    os.path.join("frontend", "TESTING.md"),
    os.path.join(".github", "workflows", "ci.yml"),
    ".gitignore",
    "README.md",
)

#: Directory and file names that are build output, dependency trees or run artifacts.
EXCLUDED_NAMES = frozenset((
    "node_modules", "__pycache__", ".pytest_cache", "test-results",
    "playwright-report", "reports", "coverage", "package-lock.json",
))

#: Directory names the citation census walk never enters. The union of what ``.gitignore``
#: suppresses, the version-control and virtual-environment directories, the browser-evidence
#: directories, and ``documentation/`` - which the census rule excludes by name because those
#: are the frozen design documents rather than files this branch ships. Verified against
#: ``git ls-files`` while the binding was written: the walk this drives and the tracked tree
#: agree on all 144 paths, in both directions. ``git`` itself is unavailable here, because the
#: conftest guards refuse a child process while a test runs.
CENSUS_EXCLUDED_DIRECTORIES = frozenset((
    ".git", ".venv-backend", "venv", "env", "ENV", "htmlcov", "documentation", "blitzy",
)) | EXCLUDED_NAMES

#: File names the walk skips: the local environment file and the coverage streams, all of them
#: gitignored, plus the ad-hoc test prefix that must never be committed.
CENSUS_EXCLUDED_FILES = frozenset((
    ".env", ".coverage", "coverage.xml", "coverage.json", "coverage.lcov",
))
CENSUS_SCRATCH_PREFIX = "blitzy_adhoc"

#: The pattern the log's own census rule names for a decision-row citation.
CENSUS_CITATION_PATTERN = r"\b[DC]\d{1,3}\b"

#: The three figures the log publishes about itself, in the order they appear.
CENSUS_PATTERNS = (
    (r"\*\*(\d+)\*\* files outside this log carry at least one `D` or `C` id", "citing"),
    (r"id — (\d+) counting\nthis file itself", "citing_with_log"),
    (r"and \*\*(\d+)\*\* link to this document", "linking"),
)

#: Prefixes a bare path token in a section F cell is resolved against, in order.
RESOLUTION_PREFIXES = ("", "backend", "frontend", "e2e", os.path.join("docs", "testing"))

#: Extensions that make a back-quoted token a candidate path rather than prose.
PATH_SUFFIXES = (
    ".py", ".ts", ".tsx", ".js", ".json", ".md", ".yml", ".html", ".css",
    ".ini", ".txt", ".coveragerc", ".gitignore",
)

#: The three section F ids withdrawn when the artifacts they named were removed.
WITHDRAWN_ROW_IDS = ("F30", "F72", "F75")

#: Rule 4's per-slide body-word ceiling for a content slide.
DECK_WORD_CAP = 40

#: Rule 4's bullet ceilings, by slide kind.
DECK_BULLET_CAPS = {"content": 4, "closing": 3}

#: Runtime pins Rule 4 names, each of which must also carry an integrity digest.
DECK_PINNED_RUNTIMES = ("reveal.js@5.1.0", "mermaid@11.4.0", "lucide@0.460.0")

#: Reveal and Mermaid settings Rule 4 requires the deck to declare.
DECK_REQUIRED_SETTINGS = (
    "hash: true",
    "controlsTutorial: false",
    "width: 1920",
    "height: 1080",
    "transition: 'slide'",
    "startOnLoad: false",
    "mermaid.run(",
)

#: Layer labels the extractor emits, in the order the dashboard documents them. Each root
#: suite is its own layer, and the fallback is a named bucket rather than a catch-all.
EXPECTED_LAYER_LABELS = (
    "Backend unit",
    "Backend integration",
    "Backend infrastructure - dependency closure",
    "Backend infrastructure - coverage gate",
    "Backend infrastructure - guard contract",
    "Backend infrastructure - dashboard producer",
    "Backend infrastructure - document contract",
    "Backend unclassified - add a prefix to BACKEND_LAYERS",
    "Frontend component",
    "Frontend unit",
)


def _read(path):
    """Return ``path`` decoded as UTF-8, with line endings normalised to ``\\n``."""
    with io.open(path, encoding="utf-8") as handle:
        return handle.read().replace("\r\n", "\n")


def _read_artifact(path):
    """Return the artifact at ``path``, decoded by its byte-order mark.

    Separate from :func:`_read` because the files this reads are produced by a shell capture
    rather than committed as documents. ``docs/testing/DASHBOARD-TEMPLATE.md`` documents the
    Windows capture as ``Tee-Object``, and PowerShell 5.1 writes UTF-16LE with a mark, which
    a UTF-8 reader cannot take either way: strictly it raises ``UnicodeDecodeError`` on the
    mark, and leniently it yields NUL-separated characters no pattern here can match, so a
    whole run's witness reads as absent and the census binding goes quietly vacuous. Mirrors
    ``decode_by_bom`` in docs/testing/dashboard-extract.py, which reads its own copies of
    these same artifacts. Row D408 of docs/testing/DECISION-LOG.md.
    """
    with io.open(path, "rb") as handle:
        raw = handle.read()

    # Longest mark first, so UTF-32LE's is never matched as UTF-16LE's prefix.
    for mark, encoding in ((b"\xff\xfe\x00\x00", "utf-32"),
                           (b"\x00\x00\xfe\xff", "utf-32"),
                           (b"\xff\xfe", "utf-16"),
                           (b"\xfe\xff", "utf-16"),
                           (b"\xef\xbb\xbf", "utf-8-sig")):
        if raw.startswith(mark):
            return raw.decode(encoding, errors="replace").replace("\r\n", "\n")

    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _active_lines(path):
    """Return the non-blank, non-comment lines of ``path``, stripped."""
    return tuple(line.strip() for line in _read(path).split("\n")
                 if line.strip() and not line.strip().startswith("#"))


def _matrix_rows():
    """Return ``{row id: (artifact cell, covers cell)}`` for every section F row."""
    rows = {}
    for line in _read(MATRIX_PATH).split("\n"):
        match = re.match(r"^\|\s*(F\d+[a-z]?)\s*\|([^|]*)\|(.*)$", line)
        if match:
            rows[match.group(1)] = (match.group(2), match.group(3))
    return rows


def _expand_braces(token):
    """Expand one ``{a,b,c}`` group in ``token`` into one token per alternative."""
    match = re.search(r"\{([^}]*)\}", token)
    if not match:
        return [token]
    expanded = []
    for alternative in match.group(1).split(","):
        expanded.extend(
            _expand_braces(token[:match.start()] + alternative.strip() + token[match.end():]))
    return expanded


def _path_tokens(cell):
    """Return the back-quoted path-shaped tokens of one markdown table cell."""
    tokens = set()
    for quoted in re.findall(r"`([^`]+)`", cell):
        for candidate in _expand_braces(quoted.strip()):
            candidate = candidate.strip().strip("*")
            if not candidate or " " in candidate:
                continue
            if candidate.endswith(PATH_SUFFIXES):
                tokens.add(candidate)
    return tokens


def _resolve(token):
    """Return the repository-relative path ``token`` names, or ``None``."""
    native = token.replace("/", os.sep)
    for prefix in RESOLUTION_PREFIXES:
        candidate = os.path.join(prefix, native) if prefix else native
        if os.path.isfile(os.path.join(REPOSITORY_ROOT, candidate)):
            return candidate.replace(os.sep, "/")
    return None


def _named_paths():
    """Return every existing path named by the artifact cell of a section F row."""
    named = set()
    for artifact, _ in _matrix_rows().values():
        for token in _path_tokens(artifact):
            resolved = _resolve(token)
            if resolved:
                named.add(resolved)
    return named


def _delivered_files():
    """Return every file of the delivered suite, walked from disk."""
    delivered = set()
    for relative in SCOPE_DIRECTORIES:
        root_directory = os.path.join(REPOSITORY_ROOT, relative)
        for directory, subdirectories, files in os.walk(root_directory):
            subdirectories[:] = [name for name in subdirectories if name not in EXCLUDED_NAMES]
            for name in files:
                if name in EXCLUDED_NAMES or name.endswith(".pyc"):
                    continue
                absolute = os.path.join(directory, name)
                delivered.add(os.path.relpath(absolute, REPOSITORY_ROOT).replace(os.sep, "/"))
    for relative in SCOPE_FILES:
        if os.path.isfile(os.path.join(REPOSITORY_ROOT, relative)):
            delivered.add(relative.replace(os.sep, "/"))
    source_root = os.path.join(REPOSITORY_ROOT, "frontend", "src")
    for directory, subdirectories, files in os.walk(source_root):
        subdirectories[:] = [name for name in subdirectories if name not in EXCLUDED_NAMES]
        for name in files:
            if ".test." in name:
                absolute = os.path.join(directory, name)
                delivered.add(os.path.relpath(absolute, REPOSITORY_ROOT).replace(os.sep, "/"))
    return delivered


def _census_files():
    """Return every path the log's citation census counts, repository-relative.

    A filesystem walk rather than ``git ls-files``, because the conftest guards refuse a child
    process while a test runs and this module states that it never invokes ``git``. The two
    were compared when this was written and agreed on all 144 paths in both directions; the
    exclusion sets are what makes that true, so a new gitignored directory has to be added to
    them or this walk starts counting artifacts.
    """
    found = set()
    for directory, subdirectories, files in os.walk(REPOSITORY_ROOT):
        subdirectories[:] = [name for name in subdirectories
                             if name not in CENSUS_EXCLUDED_DIRECTORIES]
        for name in files:
            if name in CENSUS_EXCLUDED_FILES or name.endswith(".pyc"):
                continue
            if name.startswith(CENSUS_SCRATCH_PREFIX):
                continue
            absolute = os.path.join(directory, name)
            found.add(os.path.relpath(absolute, REPOSITORY_ROOT).replace(os.sep, "/"))
    return found


def _census_readings():
    """Return ``{figure name: measured value}`` for the log's three self-census figures."""
    log_relative = os.path.join("docs", "testing", "DECISION-LOG.md").replace(os.sep, "/")
    citing, linking, citing_with_log = 0, 0, 0

    for relative in sorted(_census_files()):
        try:
            text = _read(os.path.join(REPOSITORY_ROOT, relative))
        except (IOError, OSError, UnicodeDecodeError):
            continue
        cites = re.search(CENSUS_CITATION_PATTERN, text) is not None
        if cites:
            citing_with_log += 1
            if relative != log_relative:
                citing += 1
        if "DECISION-LOG.md" in text:
            linking += 1

    return {"citing": citing, "citing_with_log": citing_with_log, "linking": linking}


def test_the_logs_citation_census_is_the_trees_own():
    """The log publishes three counts about itself; each is re-derived here.

    Before this binding nothing re-derived them, and the log said so. Two of the three had
    gone stale by one: a file gains its first citation and the paragraph does not move. The
    log's own reproduction rule is followed exactly - walk the tree skipping ``documentation/``,
    match ``\\b[DC]\\d{1,3}\\b`` for the first two and this file's own name for the third.
    """
    measured = _census_readings()
    log = _read(DECISION_LOG_PATH)

    for pattern, figure in CENSUS_PATTERNS:
        stated = int(_stated(log, pattern))
        assert stated == measured[figure], (
            "the log publishes {0} for the {1!r} census; the tree measures {2}".format(
                stated, figure, measured[figure]))


def test_the_logs_citation_census_counts_the_log_itself_exactly_once():
    """The two citation figures differ by one, and that one is this file.

    Stated separately because the pair is the part a reader uses: a document that carries no
    citation cannot be the difference, so any gap other than one means the walk changed
    meaning rather than the tree changing size.
    """
    measured = _census_readings()

    assert measured["citing_with_log"] - measured["citing"] == 1, (
        "{0} files cite a row including this log and {1} excluding it; the difference must be "
        "the log alone".format(measured["citing_with_log"], measured["citing"]))
    assert measured["linking"] >= measured["citing"], (
        "more files cite a row id ({0}) than link to the log ({1}), which would mean a "
        "citation with nowhere to resolve".format(measured["citing"], measured["linking"]))


def _deck_slides():
    """Return one ``(index, kind, markup)`` triple per ``<section>`` of the deck.

    ``index`` is one-based to match the way the deck's own comments number its
    slides. ``kind`` is read off the section's class: ``title``, ``divider`` and
    ``closing`` name themselves, and an unclassed section is a content slide.
    """
    lines = _read(DECK_PATH).split("\n")
    opens = [number for number, line in enumerate(lines) if re.search(r"<section\b", line)]
    closes = [number for number, line in enumerate(lines) if "</section>" in line]
    assert len(opens) == len(closes), "the deck has unbalanced section tags"
    slides = []
    for position, (first, last) in enumerate(zip(opens, closes), start=1):
        markup = "\n".join(lines[first:last + 1])
        for name in ("title", "divider", "closing"):
            if 'class="slide-{0}"'.format(name) in lines[first]:
                kind = name
                break
        else:
            kind = "content"
        slides.append((position, kind, markup))
    return slides


def _visible_words(markup):
    """Return the words a reader sees on ``markup``, counted the strictest way.

    Four tokenisations bracket the figures the deck was reviewed against and they
    differ only in whether the heading counts and whether a hyphenated word splits;
    all four count the raw Mermaid source rather than only its quoted labels. This
    takes the maximum of that family, so a slide inside the cap here is inside it on
    every reading. Markup, comments and HTML entities are not words; a token has to
    carry at least one alphanumeric character to count.
    """
    text = re.sub(r"<[^>]+>", " ", markup)
    text = re.sub(r"&[a-zA-Z]+;|&#\d+;", " ", text)
    text = re.sub(r"[-/\u2013\u2014]", " ", text)
    return [word for word in text.split() if re.search(r"[A-Za-z0-9]", word)]


def _deck_slides_of_kind(kind):
    """Return the ``(index, markup)`` pairs of every deck slide of ``kind``."""
    return [(index, markup) for index, slide_kind, markup in _deck_slides()
            if slide_kind == kind]


def _deck_slide_ids(kind):
    """Return short parametrisation ids, so a case name is a slide number."""
    return ["slide{0}".format(index) for index, _markup in _deck_slides_of_kind(kind)]


def _self_declared_whole_supersessions():
    """Return ``{row id: (superseder, …)}`` for rows whose own head declares it.

    The pattern is deliberately narrow: the Decision cell has to *open* with
    ``Superseded by``, optionally inside the log's square-bracket annotation. Every row
    superseded only in part opens with ``[The <something> half is superseded by …``
    instead, so the two forms are distinguishable without reading the qualifier.
    """
    found = {}
    for line in _read(DECISION_LOG_PATH).split("\n"):
        match = re.match(
            r"^\|\s*(D\d+)\s*\|\s*\*\*\[?Superseded by ((?:D\d+[, ]*(?:and )?)+)", line)
        if match:
            found[match.group(1)] = tuple(re.findall(r"D\d+", match.group(2)))
    return found


def _cited_rows(line):
    """Return the decision-row ids a single line of prose cites."""
    return {"D" + number for number in re.findall(r"\bD(\d+)\b", line)}


def _stated(document, pattern):
    """Return the single capture of ``pattern`` in ``document``, asserting uniqueness."""
    found = re.findall(pattern, document)
    assert len(found) == 1, "expected exactly one match for {0!r}, found {1}".format(
        pattern, found)
    return found[0]


# --------------------------------------------------------------------------- #
# Counts stated in prose, against the artifact they count                     #
# --------------------------------------------------------------------------- #

def test_gitignore_pattern_total_matches_the_matrix():
    """F39's pattern total is the number of active lines in ``.gitignore``."""
    matrix = _read(MATRIX_PATH)

    stated = int(_stated(matrix, r"Infrastructure: (\d+) active patterns covering"))

    assert stated == len(_active_lines(GITIGNORE_PATH))


def test_gitignore_anchored_split_matches_the_matrix():
    """F39's anchored and unanchored counts are the split the file actually has."""
    patterns = _active_lines(GITIGNORE_PATH)
    anchored = [pattern for pattern in patterns if "/" in pattern.rstrip("/")]
    unanchored = [pattern for pattern in patterns if "/" not in pattern.rstrip("/")]
    matrix = _read(MATRIX_PATH)

    assert "Twelve rules are path-anchored" in matrix
    assert "the remaining fourteen" in matrix
    assert (len(anchored), len(unanchored)) == (12, 14)


def test_gitignore_patterns_enumerated_in_the_matrix_are_the_delivered_ones():
    """Every pattern F39 lists exists, and every delivered pattern is listed."""
    patterns = set(_active_lines(GITIGNORE_PATH))
    row = [line for line in _read(MATRIX_PATH).split("\n") if line.startswith("| F39 |")]
    assert len(row) == 1
    listed = {token.strip() for token in re.findall(r"`([^`]+)`", row[0])}

    assert patterns.issubset(listed)


def test_gitignore_suppresses_only_the_two_generated_lockfiles():
    """A bare rule would suppress a committed lockfile at any depth, silently.

    The delivery does not commit either lockfile (AAP §0.6.2), so both are output
    of a documented ``npm install`` and are ignored - but only at the two paths
    that have a manifest. The Jest counterpart of this case is
    ``frontend/src/test-utils/dependency-closure.test.ts``; this one keeps the
    property asserted on a host that never installed the frontend tree.
    """
    lockfile_rules = [pattern for pattern in _active_lines(GITIGNORE_PATH)
                      if "package-lock" in pattern]

    assert sorted(lockfile_rules) == ["e2e/package-lock.json",
                                      "frontend/package-lock.json"]
    assert [rule for rule in lockfile_rules if "/" not in rule] == [], (
        "a bare package-lock.json rule would also suppress a committed lockfile")


def test_manifest_pin_census_matches_the_matrix():
    """H1's active-line and pin counts are the manifest's own."""
    active = _active_lines(MANIFEST_PATH)
    pins = [line for line in active if "==" in line]
    matrix = _read(MATRIX_PATH)

    stated_active, stated_pins = _stated(
        matrix, r"`backend/requirements-dev\.txt` \((\d+) active lines, all (\d+) exact pins")

    assert (int(stated_active), int(stated_pins)) == (len(active), len(pins))


def _manifest_sections():
    """Return ``{section heading: [pinned lines]}`` for the manifest's own partition."""
    sections, current = {}, None
    for line in _read(MANIFEST_PATH).split("\n"):
        stripped = line.strip()
        if stripped in MANIFEST_SECTIONS:
            current = stripped
            sections[current] = []
        elif stripped and not stripped.startswith("#") and "==" in stripped:
            assert current is not None, "{0!r} precedes every section heading".format(stripped)
            sections[current].append(stripped)
    return sections


def test_every_document_publishes_the_same_manifest_pin_census():
    """Three documents published 25 while a fourth published 26 - only the fourth was bound.

    Every phrasing is read, wherever it appears, and all of them are held to the manifest's own
    active-line count. Binding one document's wording left the other three free to drift, which
    is what happened when a pin was added.
    """
    active = _active_lines(MANIFEST_PATH)
    pins = [line for line in active if "==" in line]
    assert len(pins) == len(active), (
        "the census tests assume every active manifest line is an exact pin; "
        "{0} of {1} are".format(len(pins), len(active)))

    stated = {}
    for relative in FRONTEND_RESULT_DOCUMENTS:
        path = os.path.join(REPOSITORY_ROOT, relative)
        if not os.path.isfile(path):
            continue
        for number, line in enumerate(_read(path).split("\n"), 1):
            for pattern in MANIFEST_CENSUS_PATTERNS:
                for figure in re.findall(pattern, line):
                    stated.setdefault(int(figure), []).append(
                        "{0}:{1}".format(relative, number))

    assert stated, "no document publishes the manifest's pin census"
    assert set(stated) == {len(active)}, (
        "documents publish a manifest pin census the manifest does not have "
        "({0} active lines): {1}".format(len(active), stated))


def test_the_published_manifest_split_is_the_manifests_own_partition():
    """The README's "N test-stack and M runtime" split is the file's two sections, counted."""
    sections = _manifest_sections()
    assert sorted(sections) == sorted(MANIFEST_SECTIONS), (
        "the manifest no longer carries both section headings: {0}".format(sorted(sections)))

    stated_test, stated_runtime = _stated(
        _read(os.path.join(REPOSITORY_ROOT, "README.md")), MANIFEST_SPLIT_PATTERN)

    assert int(stated_test) == len(sections[MANIFEST_SECTIONS[0]])
    assert int(stated_runtime) == len(sections[MANIFEST_SECTIONS[1]])
    assert int(stated_test) + int(stated_runtime) == len(_active_lines(MANIFEST_PATH)), (
        "the published split does not account for every active manifest line")


def test_manifest_case_count_matches_the_matrix():
    """H1's case count is the count the suite's own parametrisation produces."""
    pins = [line for line in _active_lines(MANIFEST_PATH) if "==" in line]
    matrix = _read(MATRIX_PATH)

    stated_total = int(_stated(matrix, r"\*\*(\d+) cases pass\*\*: \d+ installed-version"))
    stated_pins = int(_stated(matrix, r"cases pass\*\*: (\d+) installed-version assertions"))
    providers = int(_stated(matrix, r"(\d+) module-provider assertions"))
    rejections = int(_stated(matrix, r"(\d+) parametrised non-exact-pin rejection forms"))
    singles = int(_stated(matrix, r"and (\d+) single cases covering"))

    assert stated_pins == len(pins)
    assert stated_total == stated_pins + providers + rejections + singles


# --------------------------------------------------------------------------- #
# Section F row census                                                        #
# --------------------------------------------------------------------------- #

def test_section_f_row_count_matches_the_header_prose():
    """The header prose states the number of section F rows the document carries."""
    matrix = _read(MATRIX_PATH)

    stated = int(_stated(matrix, r"The (\d+) rows below therefore name"))

    assert stated == len(_matrix_rows())


def test_section_f_row_count_matches_the_completeness_table():
    """The completeness table restates the same row count as the header prose."""
    matrix = _read(MATRIX_PATH)

    header = int(_stated(matrix, r"The (\d+) rows below therefore name"))
    table = int(_stated(matrix, r"\| \u00a7F rows \| \*\*(\d+)\*\* \|"))

    assert header == table == len(_matrix_rows())


def test_withdrawn_row_ids_are_exactly_the_absent_ones():
    """The ids the document calls withdrawn are the ids missing from the sequence."""
    present = {int(re.match(r"F(\d+)", row_id).group(1)) for row_id in _matrix_rows()}
    absent = ["F{0}".format(number)
              for number in range(1, max(present) + 1) if number not in present]

    assert tuple(absent) == WITHDRAWN_ROW_IDS
    for row_id in WITHDRAWN_ROW_IDS:
        assert row_id in _read(MATRIX_PATH)


def test_row_ids_are_unique():
    """No section F id is used twice, which a count alone would not catch."""
    ids = [re.match(r"^\|\s*(F\d+[a-z]?)\s*\|", line).group(1)
           for line in _read(MATRIX_PATH).split("\n")
           if re.match(r"^\|\s*F\d+[a-z]?\s*\|", line)]

    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# Path ownership, in both directions                                          #
# --------------------------------------------------------------------------- #

def test_every_delivered_file_is_named_by_a_section_f_row():
    """Direction B closes: no file of the suite is missing from the census."""
    unowned = sorted(_delivered_files() - _named_paths())

    assert unowned == [], "no section F row names: {0}".format(unowned)


def test_every_path_a_section_f_row_names_exists():
    """A row that names a path which was removed is a stale row."""
    missing = []
    for row_id, (artifact, _) in sorted(_matrix_rows().items()):
        for token in _path_tokens(artifact):
            if _resolve(token) is None:
                missing.append((row_id, token))

    assert missing == [], "section F rows naming a path that does not exist: {0}".format(missing)


def test_named_path_count_matches_the_completeness_table():
    """The completeness table's named-path figure is the census it describes."""
    matrix = _read(MATRIX_PATH)

    stated = int(_stated(matrix, r"\| Change-set paths named in \u00a7F \| \*\*(\d+)\*\* \|"))

    assert stated == len(_named_paths())


def test_completeness_table_arithmetic_closes():
    """Distinct paths minus named paths is the number of exceptions stated below it."""
    matrix = _read(MATRIX_PATH)

    paths = int(_stated(matrix, r"\| Distinct change-set paths \| \*\*(\d+)\*\* \|"))
    named = int(_stated(matrix, r"\| Change-set paths named in \u00a7F \| \*\*(\d+)\*\* \|"))
    difference, count = _stated(
        matrix, r"\*\*(\d+) \u2212 \d+ = (\d+), and all four are named\.\*\*")

    assert int(difference) == paths
    assert int(count) == paths - named == 4


def test_change_set_entry_and_operation_figures_differ_by_the_single_rename():
    """The rename is one entry and two operations, which is the only source of the gap."""
    matrix = _read(MATRIX_PATH)

    entries = int(_stated(matrix, r"\| Change-set entries \| \*\*(\d+)\*\* \|"))
    operations = int(_stated(matrix, r"\| Logical operations \| \*\*(\d+)\*\* \|"))
    paths = int(_stated(matrix, r"\| Distinct change-set paths \| \*\*(\d+)\*\* \|"))

    assert operations == entries + 1
    assert paths == operations


# --------------------------------------------------------------------------- #
# Producer and template agreement                                             #
# --------------------------------------------------------------------------- #

def test_dashboard_documents_every_layer_label_the_extractor_emits():
    """A layer the extractor emits but the template omits leaves a row nobody fills."""
    extractor = _read(EXTRACTOR_PATH)
    dashboard = _read(DASHBOARD_PATH)

    emitted = set(re.findall(r'\("(Backend [a-z]+(?: - [a-z ]+)?)",\s*"tests\.', extractor))
    emitted.add(re.search(r'^BACKEND_UNCLASSIFIED_LAYER = "([^"]+)"', extractor, re.M).group(1))
    emitted.update(re.findall(r'return "(Frontend (?:component|unit))"', extractor))

    assert emitted == set(EXPECTED_LAYER_LABELS)
    for label in EXPECTED_LAYER_LABELS:
        assert "| {0} |".format(label) in dashboard, label


def test_dashboard_retention_table_lists_every_workflow_upload():
    """An upload the workflow performs and the panel omits is evidence nobody looks for."""
    workflow = _read(os.path.join(REPOSITORY_ROOT, ".github", "workflows", "ci.yml"))
    dashboard = _read(DASHBOARD_PATH)

    uploaded = re.findall(r"^\s*name:\s*([a-z0-9][a-z0-9-]*)\s*$", workflow, re.M)
    artifact_names = [name for name in uploaded if "-" in name]
    assert len(artifact_names) == len(set(artifact_names)) >= 7

    for name in artifact_names:
        assert "| `{0}` |".format(name) in dashboard, name

    stated = int(_stated(dashboard, r"(\w+) uploads in all,\n?and the panel is a census").replace(
        "Seven", "7"))
    assert stated == len(artifact_names)


def test_every_result_stream_carries_a_partial_run_check():
    """A stream without one can publish a filtered run as the whole suite.

    Three streams, three different checks, because the three runners fail
    differently: the backend and the end-to-end layer compare their case count
    against an independently produced witness, while Jest re-classifies the tests
    a filter excludes as *skipped* rather than dropping them, so its count is not
    discriminating and the reason its skips carry is used instead. The extractor
    applies the same two comparisons, so a stream refused in CI is also refused
    when a dashboard is filled locally.
    """
    workflow = _read(os.path.join(REPOSITORY_ROOT, ".github", "workflows", "ci.yml"))
    extractor = _read(EXTRACTOR_PATH)
    dashboard = _read(DASHBOARD_PATH)

    assert "while collection found $collected" in workflow, "backend check is missing"
    assert "while discovery found $discovered" in workflow, "end-to-end check is missing"
    assert "'BLOCKED:' frontend/reports/jest-junit.xml" in workflow, (
        "the frontend check no longer counts the reasoned-skip marker")
    assert "state a BLOCKED: reason" in workflow, (
        "the frontend check reports no actionable message")

    for function in ("partial_stream_reason", "unreasoned_skip_reason"):
        assert "def {0}(".format(function) in extractor, function
        assert "{0}(".format(function) in extractor.split("def collect(")[1], (
            "collect() does not apply {0}".format(function))

    assert "Three workflow steps additionally read the JUnit streams" in dashboard


def _required_artifacts():
    """The artifact contract ``--require-all`` enforces, as ``(constant, path)`` pairs."""
    extractor = _read(EXTRACTOR_PATH)

    block = re.search(r"^REQUIRED[^=]*=\s*\((.*?)\)\n", extractor, re.S | re.M).group(1)
    constants = re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", block)
    assert len(constants) == len(set(constants)) >= 11

    pairs = []
    for constant in constants:
        value = re.search(r'^{0} = "([^"]+)"'.format(constant), extractor, re.M)
        assert value is not None, constant
        pairs.append((constant, value.group(1)))
    return pairs


def test_dashboard_names_every_required_artifact_the_extractor_requires():
    """A required artifact the dashboard does not name has no documented source."""
    dashboard = _read(DASHBOARD_PATH)

    for constant, relative in _required_artifacts():
        assert relative in dashboard, "{0} ({1})".format(relative, constant)


def _resolve_against(current, target):
    """``cd`` and redirection-path resolution for both shells, in one form."""
    parts = [] if current == "." else current.split("/")
    for segment in target.replace("\\", "/").split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts:
                parts.pop()
        else:
            parts.append(segment)
    return "/".join(parts) or "."


def _producer_blocks():
    """The two shell blocks section 1 gives as the way to produce every artifact.

    Selected by content rather than by position, so adding a section above them
    cannot silently select something else: a producer block is one that creates
    the backend readiness output.
    """
    dashboard = _read(DASHBOARD_PATH)

    blocks = {}
    for language in ("bash", "powershell"):
        bodies = [body for body in re.findall(
            r"^```{0}\n(.*?)^```".format(language), dashboard, re.S | re.M)
            if "collect-only.txt" in body]
        assert len(bodies) == 1, "{0}: {1} candidate blocks".format(language, len(bodies))
        blocks[language] = bodies[0]
    return blocks


def _files_written(body):
    """Every path a producer block redirects into, resolved against its own ``cd``.

    Neither block can be read one line at a time, and neither can be read without
    modelling how far a ``cd`` reaches. The POSIX one continues a command with a
    backslash, so a ``cd`` and the redirection it governs sit on different physical
    lines, and it wraps each command in a subshell, so that ``cd`` is undone at the
    closing parenthesis -- carrying it forward instead resolves the next relative
    ``cd`` against it and yields nonsense like ``backend/frontend/reports``. The
    PowerShell one uses no subshell and changes directory statefully, so one ``cd``
    governs every later redirection until the next one. Tracking parentheses as a
    directory stack models both. Comments are stripped first, so a commented-out
    example cannot satisfy the contract.
    """
    joined = body.replace("\\\n", " ")
    joined = "\n".join(line.split("#")[0] for line in joined.split("\n"))

    directory, enclosing, written = ".", [], []
    for match in re.finditer(r"(?P<enter>\()|(?P<leave>\))"
                             r"|\bcd\s+(?P<directory>[\w./\\-]+)"
                             r"|\b(?:Tee-Object|tee)\s+(?P<path>[\w./\\-]+)", joined):
        if match.group("enter"):
            enclosing.append(directory)
        elif match.group("leave"):
            directory = enclosing.pop() if enclosing else "."
        elif match.group("directory"):
            directory = _resolve_against(directory, match.group("directory"))
        else:
            written.append(_resolve_against(directory, match.group("path")))
    return written


def test_both_producer_blocks_create_every_required_text_artifact():
    """A text artifact no producer command writes cannot be produced from the document.

    The section 2 census names every artifact but runs nothing, so a name there is
    not evidence that a command creates it -- which is how the frontend discovery
    census came to be required by ``--require-all``, named by the census, and
    created by neither block, leaving a reader who followed the document exactly
    unable to fill the dashboard. Full paths are compared rather than basenames:
    ``frontend/reports/list-tests.txt`` and ``e2e/reports/list-tests.txt`` differ
    only in their directory, so a basename check passes while one of them is
    missing. Both shells are required to write the same set, because an instruction
    added to one of them is not a cross-platform instruction.
    """
    required = [path for _, path in _required_artifacts() if path.endswith(".txt")]
    assert len(required) >= 5, required

    written = {}
    for language, body in _producer_blocks().items():
        written[language] = _files_written(body)
        for relative in required:
            assert relative in written[language], (
                "the {0} producer block writes no {1}; it writes {2}".format(
                    language, relative, sorted(set(written[language]))))

    assert set(written["bash"]) == set(written["powershell"]), (
        "the producer blocks do not create the same files -- POSIX only {0}, "
        "PowerShell only {1}".format(
            sorted(set(written["bash"]) - set(written["powershell"])),
            sorted(set(written["powershell"]) - set(written["bash"]))))


# --------------------------------------------------------------------------- #
# One end-to-end census, published identically everywhere                     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("relative", CITING_DOCUMENTS, ids=CITING_DOCUMENT_IDS)
def test_every_numeric_e2e_census_claim_states_the_published_count(relative):
    """A count copied into a second document and never re-swept is the defect here."""
    path = os.path.join(REPOSITORY_ROOT, relative)
    if not os.path.isfile(path):
        pytest.skip("{0} is not present".format(relative))
    document = _read(path)

    wrong = []
    for pattern in E2E_NUMERIC_CLAIMS:
        for found in re.finditer(pattern, document):
            if int(found.group(1)) != E2E_PUBLISHED_TESTS:
                wrong.append((pattern, found.group(0)))
            if len(found.groups()) > 1 and int(found.group(2)) != E2E_PUBLISHED_SPECS:
                wrong.append((pattern, found.group(0)))

    assert wrong == [], "{0} publishes an E2E census other than {1} in {2} files: {3}".format(
        relative, E2E_PUBLISHED_TESTS, E2E_PUBLISHED_SPECS, wrong)


@pytest.mark.parametrize("relative", CITING_DOCUMENTS, ids=CITING_DOCUMENT_IDS)
def test_every_spelled_out_e2e_census_claim_states_the_published_count(relative):
    """The same rule for the prose form, which is where the deck stated it wrongly."""
    path = os.path.join(REPOSITORY_ROOT, relative)
    if not os.path.isfile(path):
        pytest.skip("{0} is not present".format(relative))
    document = _read(path)

    wrong = []
    for pattern in E2E_WORD_CLAIMS:
        for found in re.finditer(pattern, document):
            word = found.group(1).lower()
            assert word in NUMBER_WORDS, "unrecognised number word {0!r} in {1}".format(
                word, relative)
            if NUMBER_WORDS[word] != E2E_PUBLISHED_TESTS:
                wrong.append(found.group(0))

    assert wrong == [], "{0} spells the E2E census as something other than {1}: {2}".format(
        relative, E2E_PUBLISHED_TESTS, wrong)


def _e2e_discovered_census():
    """Return ``(cases, files)`` from the retained discovery listing, or ``None``.

    The listing is the independent witness of how large the E2E layer is. It is produced by
    ``npm run test:list``, which pins ``--reporter=line`` and so writes no result stream,
    and it is never written by a run that executes tests. That makes it the one artifact
    against which a retained result stream can be judged whole or partial.
    """
    if not os.path.isfile(E2E_LIST_TESTS_PATH):
        return None
    total = re.search(E2E_DISCOVERY_TOTAL, _read_artifact(E2E_LIST_TESTS_PATH))
    if total is None:
        return None
    return int(total.group(1)), int(total.group(2))


def test_the_published_e2e_census_is_the_retained_streams_own_count():
    """When a *whole* run's evidence is present, the published number is bound to it.

    Both artifacts this reads are gitignored and are produced by a different layer on a
    different runner, so the binding is only sound while the result stream is the suite. A
    documented targeted run -- one spec, one ``-g`` title, one ``--last-failed`` -- leaves a
    smaller non-zero count that no presence check can tell apart from a full run, and
    asserting the published census against it reports a document defect that does not exist.
    The discovery listing beside it is the witness, so the two are compared first and the
    case is withdrawn by name when they disagree rather than failing this suite for
    something no document said.
    """
    if not os.path.isfile(E2E_JUNIT_PATH):
        pytest.skip("e2e/reports/e2e-junit.xml is gitignored and absent in a fresh clone")

    root = re.search(r'<testsuites[^>]*\stests="(\d+)"', _read_artifact(E2E_JUNIT_PATH))

    assert root is not None, "the retained E2E stream declares no root case count"
    retained = int(root.group(1))
    discovered = _e2e_discovered_census()

    if discovered is None:
        pytest.skip(
            "e2e/reports/list-tests.txt is absent, so nothing here can tell a whole run "
            "from a targeted one; run `npm run test:list` in e2e/ to retain the witness")
    if retained != discovered[0]:
        pytest.skip(
            "the retained stream declares {0} of the {1} cases discovery reports, so it is "
            "a targeted run rather than the suite; re-run `npm test` in e2e/ to rebind "
            "it".format(retained, discovered[0]))

    assert retained == E2E_PUBLISHED_TESTS
    assert discovered == (E2E_PUBLISHED_TESTS, E2E_PUBLISHED_SPECS)


@pytest.mark.parametrize("script", PARTIAL_CAPABLE_E2E_SCRIPTS)
def test_every_partial_capable_e2e_script_pins_a_reporter_override(script):
    """A script that can run a subset must not be able to write the canonical stream.

    ``e2e/playwright.config.ts`` declares the JUnit reporter, so every unqualified
    invocation writes ``e2e/reports/e2e-junit.xml`` -- including a one-spec run and an
    interactive one. Pinning a reporter on the command line replaces that list, which is the
    same neutraliser the backend readiness probe and ``test:load`` already apply.
    """
    manifest = json.loads(_read(E2E_MANIFEST_PATH))
    body = manifest["scripts"].get(script)

    assert body is not None, "e2e/package.json declares no {0} script".format(script)
    assert E2E_REPORTER_OVERRIDE in body, (
        "{0} runs {1!r}, which writes the configured reporters and would replace the "
        "canonical result stream with a partial one".format(script, body))
    assert script in _read(E2E_README_PATH), (
        "{0} is not documented in e2e/README.md".format(script))


@pytest.mark.parametrize("encoding", ("utf-8", "utf-8-sig", "utf-16"))
def test_the_e2e_witness_is_read_however_the_capture_encoded_it(tmp_path, monkeypatch,
                                                                encoding):
    """The witness has to survive both documented captures, or the binding above goes quiet.

    ``bash`` redirection writes UTF-8 and PowerShell 5.1's ``Tee-Object`` writes UTF-16LE
    with a mark, and the dashboard documents both. A UTF-8 reader fails the second one twice
    over: strictly it raises on the mark, and leniently it yields NUL-separated characters
    :data:`E2E_DISCOVERY_TOTAL` cannot match, which withdraws the census case on every
    Windows run and reports nothing. Each documented encoding is therefore exercised against
    the real helper rather than against a copy of its logic.
    """
    listing = tmp_path / "list-tests.txt"
    body = ("Listing tests:\n"
            "  [chromium] > tests/dashboard.spec.ts:9:5 > renders the feed\n"
            "Total: {0} tests in {1} files\n".format(E2E_PUBLISHED_TESTS,
                                                     E2E_PUBLISHED_SPECS))
    listing.write_bytes(body.encode(encoding))
    monkeypatch.setitem(globals(), "E2E_LIST_TESTS_PATH", str(listing))

    assert _e2e_discovered_census() == (E2E_PUBLISHED_TESTS, E2E_PUBLISHED_SPECS)


# --------------------------------------------------------------------------- #
# The completeness prose, against the table beside it                         #
# --------------------------------------------------------------------------- #

def test_the_completeness_prose_states_the_gated_operation_total():
    """The prose figure and the machine-checked table have to be the same number."""
    matrix = _read(MATRIX_PATH)

    prose = int(_stated(matrix, r"reports \*\*(\d+)\n?\s*operations:"))
    denominator = int(_stated(matrix, r"That (\d+) is the denominator"))
    table = int(_stated(matrix, r"\| Logical operations \| \*\*(\d+)\*\* \|"))

    assert prose == denominator == table


def test_the_completeness_prose_operation_split_sums_to_its_total():
    """Additions plus modifications plus deletions is the total it is stated beside."""
    matrix = _read(MATRIX_PATH)

    total = int(_stated(matrix, r"reports \*\*(\d+)\n?\s*operations:"))
    additions, modifications, deletions = _stated(
        matrix, r"operations: (\d+) additions, (\d+) modifications, (\d+) deletions\*\*")

    assert int(additions) + int(modifications) + int(deletions) == total


def test_the_completeness_prose_accounts_for_every_operation():
    """The frozen-plan paths plus the remediation extras are the whole change set."""
    matrix = _read(MATRIX_PATH)

    total = int(_stated(matrix, r"reports \*\*(\d+)\n?\s*operations:"))
    planned = NUMBER_WORDS[
        _stated(matrix, r"([A-Za-z-]+) of those paths are the frozen plan").lower()]
    extras = NUMBER_WORDS[_stated(matrix, r"the remaining ([a-z-]+) are artifacts").lower()]

    assert planned + extras == total


# --------------------------------------------------------------------------- #
# Cross-references to a wholly superseded decision                            #
# --------------------------------------------------------------------------- #

def test_every_wholly_superseded_row_the_log_declares_is_registered():
    """The map cannot silently miss a supersession the log states in the usual form."""
    declared = _self_declared_whole_supersessions()

    assert declared, "the head pattern matched no row - the log's convention changed"
    missing = sorted(set(declared) - set(WHOLE_ROW_SUPERSESSIONS))
    assert missing == [], "not registered in WHOLE_ROW_SUPERSESSIONS: {0}".format(missing)
    for row_id, superseders in declared.items():
        registered = WHOLE_ROW_SUPERSESSIONS[row_id]
        assert set(superseders).issubset(set(registered)), row_id


def test_every_registered_supersession_is_stated_by_the_log():
    """A pair in the map that the log does not state would be an invented reversal."""
    log = _read(DECISION_LOG_PATH)
    declared = _self_declared_whole_supersessions()

    for row_id, superseders in sorted(WHOLE_ROW_SUPERSESSIONS.items()):
        if row_id in declared:
            continue
        # Stated only in the supersession index, in the form "D273's suite half by D285".
        supported = any(
            re.search(re.escape(row_id) + r"[^.|]{0,160}?" + re.escape(superseder), log)
            for superseder in superseders)
        assert supported, "{0} is registered as superseded but the log never says so".format(
            row_id)


@pytest.mark.parametrize("relative", CITING_DOCUMENTS, ids=CITING_DOCUMENT_IDS)
def test_no_document_cites_a_wholly_superseded_row_without_its_superseder(relative):
    """A reversed ruling cited alone reads as current - the defect this exists to catch."""
    path = os.path.join(REPOSITORY_ROOT, relative)
    if not os.path.isfile(path):
        pytest.skip("{0} is not present".format(relative))

    unreconciled = []
    for number, line in enumerate(_read(path).split("\n"), 1):
        cited = _cited_rows(line)
        for row_id in sorted(cited & set(WHOLE_ROW_SUPERSESSIONS), key=lambda i: int(i[1:])):
            if not cited & set(WHOLE_ROW_SUPERSESSIONS[row_id]):
                unreconciled.append((number, row_id, WHOLE_ROW_SUPERSESSIONS[row_id]))

    assert unreconciled == [], (
        "{0} cites a wholly superseded row without its superseder: {1}".format(
            relative, unreconciled))


# --------------------------------------------------------------------------- #
# A marker a document invites the reader to grep for                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("marker", MANIFEST_MARKERS)
def test_the_security_register_quotes_a_marker_the_manifest_carries(marker):
    """The register and the manifest have to agree on the annotation, verbatim."""
    quoted_by_register = marker in _read(SECURITY_GAPS_PATH)
    carried_by_manifest = marker in _read(MANIFEST_PATH)

    assert quoted_by_register, "the security register no longer quotes {0!r}".format(marker)
    assert carried_by_manifest, "the manifest does not carry {0!r}".format(marker)


def test_the_withdrawn_exception_wording_appears_nowhere():
    """`D339`'s four-line block was withdrawn by `D292`; nothing may still promise it."""
    for relative in CITING_DOCUMENTS + (os.path.join("backend", "requirements-dev.txt"),):
        path = os.path.join(REPOSITORY_ROOT, relative)
        if os.path.isfile(path):
            assert "SECURITY EXCEPTION" not in _read(path), relative


# --------------------------------------------------------------------------- #
# The deviations put to an owner, and the backlog that must not contradict     #
# --------------------------------------------------------------------------- #

def _deviation_register():
    """Return ``{finding id: (adjudication cell, owner-ask cell)}`` for the §40 register."""
    rows = {}
    pattern = (r"^\|\s*\d+\s*\|\s*(F\d+)\s*\u2014[^|]*\|"
               r"[^|]*\|[^|]*\|([^|]*)\|([^|]*)\|\s*$")
    for line in _read(DECISION_LOG_PATH).split("\n"):
        match = re.match(pattern, line)
        if match:
            rows[match.group(1)] = (match.group(2).strip(), match.group(3).strip())
    return rows


def test_the_deviation_register_carries_exactly_the_escalated_findings():
    """One row per deviation, and no row for anything else."""
    assert sorted(_deviation_register()) == sorted(ESCALATED_DEVIATIONS)


@pytest.mark.parametrize("finding", ESCALATED_DEVIATIONS)
def test_every_deviation_states_an_adjudication_and_an_owner_ask(finding):
    """A register entry is only useful if it says which way it went and what is owed."""
    adjudication, owner_ask = _deviation_register()[finding]

    assert any(word in adjudication for word in ("Ratify", "Authorised")), (
        "{0} states no adjudication: {1!r}".format(finding, adjudication))
    assert re.search(r"D\d+", adjudication), (
        "{0} cites no decision row: {1!r}".format(finding, adjudication))
    assert len(owner_ask.split()) >= 8, (
        "{0} does not say what an owner signs off: {1!r}".format(finding, owner_ask))


def test_the_readme_routes_the_deviations_to_the_register():
    """The one list a new developer reads has to reach the register, by count and by link."""
    readme = _read(os.path.join(REPOSITORY_ROOT, "README.md"))

    assert "Owner decision, not a task" in readme
    assert "the seven places where a delivered detail differs" in readme
    assert "docs/testing/DECISION-LOG.md" in readme


def test_the_readme_backlog_agrees_with_the_delivered_pin():
    """No backlog entry may call unattempted a change the manifest already carries."""
    assert DELIVERED_PIN in _read(MANIFEST_PATH)
    version = DELIVERED_PIN.split("==")[1]
    entries = [line for line
               in _read(os.path.join(REPOSITORY_ROOT, "README.md")).split("\n")
               if line.startswith("- ") and "python-jose" in line]

    assert entries, "no backlog entry names the pin at all"
    for entry in entries:
        assert "Not attempted" not in entry, (
            "a backlog entry still calls the pin unattempted while the manifest carries "
            + DELIVERED_PIN)
    stating = [entry for entry in entries if version in entry]
    assert len(stating) == 1, (
        "expected exactly one entry to state the delivered version {0}, found {1}".format(
            version, len(stating)))



# --------------------------------------------------------------------------- #
# One suite size, published in one place at a time                            #
# --------------------------------------------------------------------------- #

def _published_figures(patterns):
    """Return ``{figure: [documents stating it]}`` across the count-publishing set."""
    stated = {}
    for relative in COUNT_PUBLISHING_DOCUMENTS:
        path = os.path.join(REPOSITORY_ROOT, relative)
        if not os.path.isfile(path):
            continue
        text = _read(path)
        for pattern in patterns:
            for figure in re.findall(pattern, text):
                stated.setdefault(int(figure), []).append(relative)
    return stated


def test_every_document_publishes_the_same_backend_collected_figure():
    """A document left behind by a growing suite is the defect this catches."""
    stated = _published_figures(COLLECTED_PATTERNS)

    assert stated, "no document states how many backend cases are collected"
    assert len(stated) == 1, "documents disagree on the collected count: {0}".format(
        {figure: sorted(set(docs)) for figure, docs in stated.items()})


def test_every_document_publishes_the_same_backend_passing_figure():
    """The same, for the number that passes rather than the number collected."""
    stated = _published_figures(PASSED_PATTERNS)

    assert stated, "no document states how many backend cases pass"
    assert len(stated) == 1, "documents disagree on the passing count: {0}".format(
        {figure: sorted(set(docs)) for figure, docs in stated.items()})


def test_the_collected_figure_is_not_below_the_passing_figure():
    """Collected has to account for the passes and the skips, never fewer."""
    collected = list(_published_figures(COLLECTED_PATTERNS))[0]
    passing = list(_published_figures(PASSED_PATTERNS))[0]

    assert collected >= passing
    assert collected - passing == 3, (
        "{0} collected minus {1} passing is not the 3 reasoned skips the documents "
        "describe".format(collected, passing))


def _frontend_readings():
    """Return ``[(document, line number, {figure: value})]`` for the frontend result.

    One entry per statement rather than one per document, so a document that contradicts
    *itself* is caught as well as one that contradicts its neighbour - which is the shape the
    defect took: two lines of the same table published a different passing figure.
    """
    readings = []
    for relative in FRONTEND_RESULT_DOCUMENTS:
        path = os.path.join(REPOSITORY_ROOT, relative)
        if not os.path.isfile(path):
            continue
        for number, line in enumerate(_read(path).split("\n"), 1):
            for pattern, fields in FRONTEND_RESULT_PATTERNS:
                for found in re.findall(pattern, line):
                    values = found if isinstance(found, tuple) else (found,)
                    readings.append(
                        (relative, number,
                         dict(zip(fields, (int(value) for value in values)))))
    return readings


def test_every_document_publishes_the_same_frontend_result():
    """Two lines of one table publishing different passing figures is the defect this catches.

    Compared field by field against the runner's committed summary line, so a phrasing that
    states only the passing figure is held to that and to nothing else.
    """
    readings = _frontend_readings()

    assert readings, "no document states the frontend suite's result"

    disagreements = []
    for figure in ("passed", "skipped", "tests", "suites", "suites_passed", "suites_skipped"):
        stated = {}
        for relative, number, reading in readings:
            if figure in reading:
                stated.setdefault(reading[figure], []).append(
                    "{0}:{1}".format(relative, number))
        if len(stated) > 1:
            disagreements.append((figure, stated))

    assert disagreements == [], "documents disagree on the frontend result: {0}".format(
        disagreements)


def test_the_published_frontend_result_closes_arithmetically():
    """Passes and skips have to account for the total, at both the case and the suite level."""
    merged = {}
    for _relative, _number, reading in _frontend_readings():
        merged.update(reading)

    for figure in ("passed", "skipped", "tests", "suites", "suites_passed", "suites_skipped"):
        assert figure in merged, "no document states the frontend {0} figure".format(figure)

    assert merged["passed"] + merged["skipped"] == merged["tests"], (
        "{0} passed plus {1} skipped is not the {2} published as the total".format(
            merged["passed"], merged["skipped"], merged["tests"]))
    assert merged["suites_passed"] + merged["suites_skipped"] == merged["suites"], (
        "{0} passing suites plus {1} skipped is not the {2} published as the suite "
        "total".format(merged["suites_passed"], merged["suites_skipped"], merged["suites"]))


def test_the_published_frontend_result_is_the_retained_streams_own():
    """The published figures are the artifact's, whenever this tree has produced one.

    Deliberately not a ``pytest.skip`` when the stream is absent: two skips already fire on a
    missing artifact, both named in the documents beside the first-pass figure, and a third
    would move that figure without adding a property. The cross-document check above always
    runs and is anchored to a committed transcript, so nothing here is left unasserted in a
    fresh clone - this case adds the tie to the machine-written stream when there is one.
    """
    if not os.path.isfile(FRONTEND_JUNIT_PATH):
        return

    stream = _read_artifact(FRONTEND_JUNIT_PATH)
    root = re.search(r'<testsuites\b[^>]*\btests="(\d+)"', stream)
    assert root, "the frontend result stream declares no root case count"

    suites = re.findall(r"<testsuite\b[^>]*>", stream)
    skipped = sum(int(_stated(suite, r'\bskipped="(\d+)"')) for suite in suites)

    merged = {}
    for _relative, _number, reading in _frontend_readings():
        merged.update(reading)

    assert merged["tests"] == int(root.group(1)), (
        "documents publish {0} frontend cases; the stream declares {1}".format(
            merged["tests"], root.group(1)))
    assert merged["suites"] == len(suites), (
        "documents publish {0} frontend suites; the stream carries {1}".format(
            merged["suites"], len(suites)))
    assert merged["skipped"] == skipped, (
        "documents publish {0} frontend skips; the stream sums {1}".format(
            merged["skipped"], skipped))
    assert merged["passed"] == int(root.group(1)) - skipped, (
        "documents publish {0} frontend passes; the stream implies {1}".format(
            merged["passed"], int(root.group(1)) - skipped))


@pytest.mark.parametrize("relative,reason", ARTIFACT_CONDITIONAL_SKIPS,
                         ids=[reason.split()[0] for _path, reason in
                              ARTIFACT_CONDITIONAL_SKIPS])
def test_each_artifact_conditional_skip_still_carries_its_stated_reason(relative, reason):
    """The documents explain the first-pass figure by naming these two skips.

    If one is removed or its reason reworded, the explanation beside the published
    figure becomes a claim about a skip that no longer exists - so the reason string
    is asserted verbatim rather than described.
    """
    source = _read(os.path.join(REPOSITORY_ROOT, relative))

    assert 'pytest.skip("{0}")'.format(reason) in source, (
        "{0} no longer skips with the reason the documents quote".format(relative))


@pytest.mark.parametrize("relative", FIRST_PASS_DOCUMENTS,
                         ids=[path.replace(os.sep, "/") for path in FIRST_PASS_DOCUMENTS])
def test_the_first_pass_figure_is_stated_where_a_reader_would_run_the_suite(relative):
    """A published figure a fresh clone cannot reproduce is a defect, not a detail.

    The warm figure is correct and stays the headline. What has to sit beside it is
    the figure a first pass produces, and the two are checked against each other and
    against the collected total rather than taken on trust: the difference between
    them is exactly the number of artifact-conditional skips, and the first pass has
    to account for the whole collection.
    """
    document = _read(os.path.join(REPOSITORY_ROOT, relative))
    conditional = len(ARTIFACT_CONDITIONAL_SKIPS)

    stated = re.findall(FIRST_PASS_PATTERN, document)
    assert stated, "{0} publishes no first-pass figure".format(relative)

    warm = list(_published_figures(PASSED_PATTERNS))[0]
    collected = list(_published_figures(COLLECTED_PATTERNS))[0]

    for passed, skipped in stated:
        passed, skipped = int(passed), int(skipped)
        assert warm - passed == conditional, (
            "{0} states {1} passing on a first pass against a warm {2}; the difference "
            "must be the {3} artifact-conditional skips".format(
                relative, passed, warm, conditional))
        assert skipped - (collected - warm) == conditional, (
            "{0} states {1} skipped on a first pass; that is not the reasoned skips plus "
            "the {2} artifact-conditional ones".format(relative, skipped, conditional))
        assert passed + skipped == collected, (
            "{0}'s first-pass figures sum to {1}, not the {2} collected".format(
                relative, passed + skipped, collected))


def test_the_documented_root_misuse_figures_account_for_the_whole_collection():
    """The one figure in the README that describes a *failing* run has to add up.

    A bare ``pytest`` from the repository root loads no configuration file, so
    ``asyncio_mode`` is off and every ``async def`` test errors. The point of
    publishing that triple is to make the failure recognisable, which it only is if
    the numbers describe the same collection the paragraph above them states.
    """
    readme = _read(os.path.join(REPOSITORY_ROOT, "README.md"))

    stated = re.findall(ROOT_MISUSE_PATTERN, readme)
    assert len(stated) == 1, "expected exactly one root-misuse triple, found {0}".format(
        stated)

    failed, passed, skipped = (int(group) for group in stated[0])
    collected = list(_published_figures(COLLECTED_PATTERNS))[0]

    assert failed > 0, "a triple describing a misuse with no failures explains nothing"
    assert failed + passed + skipped == collected, (
        "the documented root run accounts for {0} cases where {1} are collected".format(
            failed + passed + skipped, collected))


def _deck_headline_kpi():
    """Return the deck's headline KPI string, read through its own label."""
    match = re.search(
        r'<span class="kpi-value">([\d,]+)</span>\s*'
        r'<span class="kpi-label">Tests passing now</span>', _read(DECK_PATH))
    assert match, "the deck has no KPI value paired with a 'Tests passing now' label"
    return match.group(1)


def test_the_deck_headline_kpi_is_the_sum_of_the_three_streams():
    """The KPI is defined as a sum, so it is checkable rather than assertable."""
    matrix = _read(MATRIX_PATH)
    triple = re.search(r"\((\d{3,5}) backend, (\d+) frontend, (\d+) browser\)", matrix)

    assert triple, "the matrix no longer states the three stream figures"
    backend, frontend, browser = (int(group) for group in triple.groups())
    kpi = _deck_headline_kpi()

    assert int(kpi.replace(",", "")) == backend + frontend + browser, (
        "the deck publishes {0} where the three streams sum to {1}".format(
            kpi, backend + frontend + browser))
    assert browser == E2E_PUBLISHED_TESTS
    assert backend == list(_published_figures(PASSED_PATTERNS))[0]


def test_every_document_quoting_the_headline_kpi_quotes_the_same_one():
    """The KPI appears in three files; a stale copy is the failure mode."""
    kpi = _deck_headline_kpi()
    for path in (MATRIX_PATH, DASHBOARD_PATH):
        assert "`{0}`".format(kpi) in _read(path), (
            "{0} does not quote the deck's KPI {1}".format(path, kpi))


# --------------------------------------------------------------------------- #
# Deck census and provenance                                                  #
# --------------------------------------------------------------------------- #

def test_deck_section_count_matches_every_document_that_states_it():
    """The section count in the deck is what the matrix and the dashboard claim."""
    sections = len(re.findall(r"<section\b", _read(DECK_PATH)))
    matrix = _read(MATRIX_PATH)
    dashboard = _read(DASHBOARD_PATH)

    assert sections == 16
    assert "{0} sections over four slide types".format(sections) in matrix
    assert "`.reveal .slides > section` **{0}**".format(sections) in dashboard


def test_one_provenance_hash_across_every_document():
    """Every document quoting the measured commit quotes the same one."""
    quoted = set()
    for path in (MATRIX_PATH, DASHBOARD_PATH, DECISION_LOG_PATH,
                 os.path.join(REPOSITORY_ROOT, "README.md"),
                 os.path.join(REPOSITORY_ROOT, "backend", "tests", "README.md"),
                 os.path.join(REPOSITORY_ROOT, "frontend", "TESTING.md"),
                 os.path.join(REPOSITORY_ROOT, "e2e", "README.md")):
        if not os.path.isfile(path):
            continue
        quoted.update(re.findall(r"measured against `([0-9a-f]{7,40})`", _read(path)))
        quoted.update(re.findall(r"git checkout `?([0-9a-f]{7,40})`?", _read(path)))
        quoted.update(re.findall(r"provenance commit `([0-9a-f]{7,40})`", _read(path)))

    assert len(quoted) <= 1, "documents quote more than one measured commit: {0}".format(
        sorted(quoted))


# --------------------------------------------------------------------------- #
# Rule 4's numeric limits on the executive deck                               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("index,markup", _deck_slides_of_kind("content"),
                         ids=_deck_slide_ids("content"))
def test_every_content_slide_stays_within_the_body_word_cap(index, markup):
    """A content slide carries at most forty words on the strictest reading."""
    words = _visible_words(markup)

    assert len(words) <= DECK_WORD_CAP, (
        "content slide {0} carries {1} words: {2}".format(
            index, len(words), " ".join(words)))


@pytest.mark.parametrize("index,markup", _deck_slides_of_kind("content"),
                         ids=_deck_slide_ids("content"))
def test_every_content_slide_stays_within_the_bullet_cap(index, markup):
    """A content slide carries at most four bullets."""
    bullets = re.findall(r"<li\b", markup)

    assert len(bullets) <= DECK_BULLET_CAPS["content"], (
        "content slide {0} carries {1} bullets".format(index, len(bullets)))


def test_the_closing_slide_stays_within_its_bullet_cap():
    """The closing slide carries at most three bullets."""
    closing = _deck_slides_of_kind("closing")

    assert len(closing) == 1, "expected exactly one closing slide"
    bullets = re.findall(r"<li\b", closing[0][1])
    assert len(bullets) <= DECK_BULLET_CAPS["closing"], (
        "the closing slide carries {0} bullets".format(len(bullets)))


def test_every_slide_carries_a_non_text_visual():
    """No slide is text alone: each carries a diagram, icon, KPI grid, table or rule."""
    without = []
    for index, _kind, markup in _deck_slides():
        carries = ("<pre class=\"mermaid" in markup
                   or "data-lucide" in markup
                   or "kpi-grid" in markup
                   or "<table" in markup
                   or "accent-bar" in markup)
        if not carries:
            without.append(index)

    assert without == [], "slides with no non-text visual: {0}".format(without)


def test_the_deck_carries_all_four_slide_types():
    """The deck uses the title, divider, content and closing types Rule 4 names."""
    kinds = [kind for _index, kind, _markup in _deck_slides()]

    assert len(kinds) == 16
    for name in ("title", "divider", "content", "closing"):
        assert name in kinds, "the deck declares no {0} slide".format(name)
    assert kinds.count("title") == 1
    assert kinds.count("closing") == 1
    assert kinds.count("content") == 8


def test_the_deck_pins_every_third_party_runtime():
    """Each CDN runtime is version-pinned and bound to its bytes by an integrity digest."""
    deck = _read(DECK_PATH)

    for pin in DECK_PINNED_RUNTIMES:
        assert pin in deck, "the deck does not pin {0}".format(pin)
    assert len(re.findall(r"integrity=\"sha384-", deck)) == 4


def test_the_deck_declares_the_runtime_configuration_rule_four_requires():
    """The reveal and Mermaid settings Rule 4 names are present in the deck."""
    deck = _read(DECK_PATH)

    for setting in DECK_REQUIRED_SETTINGS:
        assert setting in deck, "the deck does not declare {0}".format(setting)


def test_the_deck_diagram_census_matches_the_dashboard():
    """The diagram and icon totals the dashboard reports are the deck's own."""
    deck = _read(DECK_PATH)
    dashboard = _read(DASHBOARD_PATH)
    slides = _deck_slides()
    diagrams = sum(len(re.findall(r"<pre class=\"mermaid", markup))
                   for _index, _kind, markup in slides)
    icons = re.findall(r"data-lucide=\"([^\"]+)\"", deck)
    slides_with_diagram = [index - 1 for index, _kind, markup in slides
                           if "<pre class=\"mermaid" in markup]

    assert diagrams == 6
    assert len(icons) == len(set(icons)) == 19
    assert "**{0} of {0}**".format(diagrams) in dashboard
    assert "`svg.lucide` **{0}**".format(len(icons)) in dashboard
    assert slides_with_diagram == [2, 4, 8, 10, 12, 14]
    assert "on slides {0} and {1}".format(
        ", ".join(str(number) for number in slides_with_diagram[:-1]),
        slides_with_diagram[-1]) in dashboard


def test_the_measured_slide_word_counts_match_the_decision_log():
    """The per-slide word vector the decision log states is the deck's own."""
    measured = [len(_visible_words(markup))
                for _index, markup in _deck_slides_of_kind("content")]
    log = _read(DECISION_LOG_PATH)

    stated = _stated(log, r"strictest reading are ([\d, ]+?) against a cap of 40")
    assert [int(number) for number in stated.split(",")] == measured


# --------------------------------------------------------------------------- #
# The security register's own census, and the authorities the seam pass cited  #
# five rows early                                                             #
# --------------------------------------------------------------------------- #

#: The register groups ``README.md``'s security bullet counts together: the three whose
#: exposures are all held out of reach by a clause of the frozen plan. Its larger figure is
#: every group, including the two no exclusion covers - the executive deck as a served
#: artifact, and the end-to-end harness's own development server.
REGISTER_README_GROUPS = (1, 2, 3)

#: How the register's census is published. ``README.md`` spells both figures out in one
#: sentence; ``TRACEABILITY-MATRIX.md`` F100 states the total as a numeral. Each capture is
#: named, so a document that contradicts *itself* is caught as well as one that contradicts
#: another. The log is deliberately not read here: its rows state the census each earlier
#: checkpoint measured, and D354 freezes those as history.
REGISTER_CENSUS_PATTERNS = (
    (u"There are ([a-z-]+) of them in those three categories \u2014 ([a-z-]+) rows in "
     u"the register in total", ("grouped", "total")),
    (r"(\d+) exposures in six groups", ("total",)),
)

#: Number words a register census figure may be spelled out as. Both stale values are kept
#: in the map deliberately: a regression to either then fails on its *value* rather than
#: falling out of the pattern and passing unnoticed.
REGISTER_NUMBER_WORDS = {
    "thirty": 30, "thirty-one": 31, "thirty-two": 32, "thirty-three": 33,
    "thirty-four": 34, "thirty-five": 35, "thirty-six": 36, "thirty-seven": 37,
    "thirty-eight": 38, "thirty-nine": 39, "forty": 40, "forty-one": 41,
}

#: The rows ``README.md``'s bullet names individually, with the group each is the whole of.
REGISTER_NAMED_GROUPS = ((5, "rows 24 and 25"), (6, "row 33"))

#: The rows the log's section 47 opened, each with the artifact its Decision cell names and
#: the section F row that covers that artifact. Asserted in **both** directions. Every one
#: of these was cited five rows early, and because D409 to D413 are all real rows the wrong
#: pointer read exactly like a deliberate one - which is why the pairing is machine-checked
#: here rather than left to a reader who would have to open the log to notice.
SEAM_PASS_AUTHORITIES = (
    ("F50", "D415", "tests/integration/test_http_tweets.py"),
    ("F51", "D414", "tests/integration/test_route_surface.py"),
    ("F52", "D417", "tests/integration/test_app_lifecycle.py"),
    ("F55", "D418", "frontend/src/schema/tweetSchema.test.ts"),
    ("F60", "D414", "frontend/src/services/api.test.ts"),
    ("F63", "D416", "frontend/src/components/Dashboard.test.tsx"),
)


def _register_groups():
    """Return ``{group number: (row id, ...)}``, read from the register's own headings."""
    groups = {}
    current = None
    for line in _read(SECURITY_GAPS_PATH).split("\n"):
        if line.startswith("## "):
            heading = re.match(r"^##\s+(\d+)\.\s", line)
            current = int(heading.group(1)) if heading else None
            if current is not None:
                groups.setdefault(current, [])
            continue
        row = re.match(r"^\|\s*(\d+)\s*\|", line)
        if row and current is not None:
            groups[current].append(int(row.group(1)))
    return dict((number, tuple(rows)) for number, rows in groups.items())


def _register_row_ids():
    """Return every row id in the register, across every group, sorted."""
    ids = []
    for rows in _register_groups().values():
        ids.extend(rows)
    return sorted(ids)


def _register_number(raw):
    """Return an integer for a census figure written as a numeral or spelled out."""
    if raw.isdigit():
        return int(raw)
    assert raw in REGISTER_NUMBER_WORDS, "unmapped register number word {0!r}".format(raw)
    return REGISTER_NUMBER_WORDS[raw]


def _register_readings():
    """Return ``[(where, figure name, value), ...]`` for every published census figure."""
    readings = []
    for relative in COUNT_PUBLISHING_DOCUMENTS:
        path = os.path.join(REPOSITORY_ROOT, relative)
        if not os.path.isfile(path):
            continue
        for number, line in enumerate(_read(path).split("\n"), 1):
            for pattern, names in REGISTER_CENSUS_PATTERNS:
                match = re.search(pattern, line)
                if match:
                    where = "{0}:{1}".format(relative.replace(os.sep, "/"), number)
                    for name, raw in zip(names, match.groups()):
                        readings.append((where, name, _register_number(raw)))
    return readings


def _decision_row(row_id):
    """Return the whole table line for one decision row, asserting it is unique."""
    found = [line for line in _read(DECISION_LOG_PATH).split("\n")
             if re.match(r"^\|\s*" + row_id + r"\s*\|", line)]
    assert len(found) == 1, "expected exactly one {0} row in the log, found {1}".format(
        row_id, len(found))
    return found[0]


def _decision_row_ids():
    """Return every id the log carries as the head of one of its table rows."""
    ids = set()
    for line in _read(DECISION_LOG_PATH).split("\n"):
        match = re.match(r"^\|\s*(D\d+)\s*\|", line)
        if match:
            ids.add(match.group(1))
    return ids


def test_the_register_row_ids_are_unique_and_contiguous():
    """Ids are append-only (D401), so the set has to be 1..N with nothing missing."""
    ids = _register_row_ids()

    assert len(ids) == len(set(ids)), "the register repeats a row id: {0}".format(ids)
    assert ids == list(range(1, len(ids) + 1)), (
        "the register's ids are not 1..{0}: {1}".format(len(ids), ids))


def test_every_document_publishes_the_registers_own_census():
    """The figure a reader schedules on, re-derived from the register that carries it."""
    groups = _register_groups()
    expected = {
        "total": len(_register_row_ids()),
        "grouped": sum(len(groups[number]) for number in REGISTER_README_GROUPS),
    }

    readings = _register_readings()
    assert readings, "no document publishes the security register's census any more"

    wrong = [reading for reading in readings if reading[2] != expected[reading[1]]]
    assert wrong == [], (
        "the register measures {0}; these disagree: {1}".format(expected, wrong))


def test_the_registers_grouped_and_total_figures_close_arithmetically():
    """The two published figures differ by exactly the groups no plan clause covers."""
    groups = _register_groups()
    uncovered = sum(len(rows) for number, rows in groups.items()
                    if number not in REGISTER_README_GROUPS)
    published = dict((name, value) for _where, name, value in _register_readings())

    assert published["total"] - published["grouped"] == uncovered, (
        "published total {0} minus grouped {1} is not the {2} row(s) outside those "
        "groups".format(published["total"], published["grouped"], uncovered))


@pytest.mark.parametrize(
    "group,phrase", REGISTER_NAMED_GROUPS,
    ids=["group{0}".format(entry[0]) for entry in REGISTER_NAMED_GROUPS])
def test_the_rows_the_readme_names_individually_are_their_whole_group(group, phrase):
    """A row appended to either group makes the bullet's parenthetical wrong, loudly."""
    rows = _register_groups()[group]
    spelled = "row{0} {1}".format(
        "s" if len(rows) > 1 else "", " and ".join(str(row) for row in rows))

    assert spelled == phrase, (
        "group {0} is now {1}, but README.md still names {2!r}".format(group, rows, phrase))
    assert phrase in _read(os.path.join(REPOSITORY_ROOT, "README.md")), (
        "README.md no longer names {0!r}".format(phrase))


@pytest.mark.parametrize("row,decision,artifact", SEAM_PASS_AUTHORITIES,
                         ids=[entry[0] for entry in SEAM_PASS_AUTHORITIES])
def test_each_seam_pass_row_cites_the_decision_that_decided_it(row, decision, artifact):
    """Both directions, because a pointer at a real but unrelated row is invisible."""
    artifact_cell, covers_cell = _matrix_rows()[row]

    assert decision in _cited_rows(covers_cell), (
        "{0} does not cite {1}; it cites {2}".format(
            row, decision, sorted(_cited_rows(covers_cell))))
    assert artifact in artifact_cell + covers_cell, (
        "{0} is not the section F row about {1}".format(row, artifact))

    log_row = _decision_row(decision)
    assert artifact in log_row, (
        "{0} does not name {1}, so it cannot be {2}'s authority".format(
            decision, artifact, row))


@pytest.mark.parametrize("relative", CITING_DOCUMENTS, ids=CITING_DOCUMENT_IDS)
def test_every_decision_row_a_document_cites_exists(relative):
    """A citation of an id the log does not carry reads exactly like one that it does."""
    path = os.path.join(REPOSITORY_ROOT, relative)
    if not os.path.isfile(path):
        pytest.skip("{0} is not present".format(relative))

    present = _decision_row_ids()
    missing = sorted((row for row in _cited_rows(_read(path)) if row not in present),
                     key=lambda row: int(row[1:]))

    assert missing == [], "{0} cites decision rows the log does not carry: {1}".format(
        relative, missing)


#: Cross-references that name a security-register row **by number**, as a pattern that
#: captures the number, paired with a phrase the register row itself carries. The number is
#: never written here: it is looked up in the register by subject, so moving a subject to
#: another row moves every citation of it with a red test. This is the half
#: :data:`SEAM_PASS_AUTHORITIES` cannot see, and a negative validation found it missing -
#: reverting F63's "row 38" to "row 33" left every other binding green, because row 33 is a
#: real row about the harness dev server and only its *subject* distinguishes it.
REGISTER_CROSS_REFERENCES = (
    (r"unhandled-rejection leak whose measurement lives in `SECURITY-GAPS\.md` row (\d+)",
     "26 unhandled rejections", os.path.join("docs", "testing", "TRACEABILITY-MATRIX.md")),
    (r"submitted with every character intact \(`SECURITY-GAPS\.md` row (\d+)",
     "40,068-byte request", os.path.join("docs", "testing", "TRACEABILITY-MATRIX.md")),
    (r"`--require-hashes` \u2014 is `SECURITY-GAPS\.md` row (\d+)",
     "--only-binary=:all:", os.path.join("docs", "testing", "TRACEABILITY-MATRIX.md")),
    (r"\| `D416`, `SECURITY-GAPS\.md` row (\d+) \|",
     "26 unhandled rejections", os.path.join("frontend", "TESTING.md")),
    (r"recorded in \u00a723, `SECURITY-GAPS\.md` row (\d+) and `frontend/TESTING\.md`",
     "26 unhandled rejections", os.path.join("docs", "testing", "DECISION-LOG.md")),
    (r"records\. Also `SECURITY-GAPS\.md` row (\d+)\.",
     "26 unhandled rejections", os.path.join("docs", "testing", "DECISION-LOG.md")),
)

#: Parametrisation ids for the cross-references: the document and the row's subject, because
#: three of them are in one file and a filename id would collide.
REGISTER_CROSS_REFERENCE_IDS = [
    "{0}-{1}".format(os.path.basename(entry[2]), entry[1].split()[0].strip("-"))
    for entry in REGISTER_CROSS_REFERENCES
]


def _register_row_about(subject):
    """Return the register row id whose own text carries ``subject``, asserting uniqueness."""
    found = []
    for line in _read(SECURITY_GAPS_PATH).split("\n"):
        row = re.match(r"^\|\s*(\d+)\s*\|", line)
        if row and subject in line:
            found.append(int(row.group(1)))
    assert len(found) == 1, "expected one register row carrying {0!r}, found {1}".format(
        subject, found)
    return found[0]


@pytest.mark.parametrize("pattern,subject,relative", REGISTER_CROSS_REFERENCES,
                         ids=REGISTER_CROSS_REFERENCE_IDS)
def test_every_register_cross_reference_names_the_row_its_subject_is_on(
        pattern, subject, relative):
    """Derive the row number from the register; never let a document type it by hand."""
    expected = _register_row_about(subject)
    document = _read(os.path.join(REPOSITORY_ROOT, relative))
    found = [int(number) for number in re.findall(pattern, document)]

    assert found, "{0} no longer carries the cross-reference {1!r}".format(relative, pattern)
    assert set(found) == set([expected]), (
        "{0} points at row(s) {1}, but the register puts {2!r} on row {3}".format(
            relative, sorted(set(found)), subject, expected))


# --------------------------------------------------------------------------- #
# Declaration-level parity between the deck's inline <style> and the canonical  #
# theme Rule 4 names                                                          #
# --------------------------------------------------------------------------- #

#: The reusable reference copy at the path Rule 4 names. It is never loaded: the deck is a
#: single self-contained file and carries the same declarations inline, because Rule 4 wants
#: both a canonical stylesheet and one self-contained file and the two pull against each
#: other. That is exactly why the parity needs a check - F70 claimed it was exact while
#: `.deck-diagram-sm` read `margin: 20px auto 0` against the deck's `20px 0 0`.
DECK_THEME_PATH = os.path.join(
    REPOSITORY_ROOT, "blitzy-deck", "references", "blitzy-reveal-theme.css")

#: How ``TRACEABILITY-MATRIX.md`` F70 publishes the parity census: custom properties, then
#: rule blocks, then the selector groups they resolve to. Derived from the stylesheets.
DECK_PARITY_CENSUS_PATTERN = (
    r"the same (\d+) `:root` custom\s+properties with identical values, the same (\d+) rule "
    r"blocks resolving to the same (\d+)\s+selector groups")


def _deck_inline_style():
    """Return the deck's single inline stylesheet, asserting that it is single."""
    blocks = re.findall(r"<style[^>]*>(.*?)</style>", _read(DECK_PATH), re.S)
    assert len(blocks) == 1, (
        "Rule 4 wants one self-contained file; the deck carries {0} <style> blocks".format(
            len(blocks)))
    return blocks[0]


def _css_rules(css):
    """Return ``[(at-rule context, selector group, (declaration, ...)), ...]``.

    Comments are stripped and whitespace collapsed before comparing, which is what lets the
    reference copy keep the longer explanatory blocks F70 describes while still being held to
    the same declarations. Declarations are sorted, so ordering inside a block is not a
    difference. One level of at-rule nesting is enough: neither file nests one inside another.
    """
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    found = []
    index, context, depth = 0, "", 0
    while index < len(css):
        brace = css.find("{", index)
        if brace == -1:
            break
        prelude = css[index:brace].strip()
        body_end = css.find("}", brace)
        limit = body_end if body_end != -1 else len(css)
        if prelude.startswith("@") and "{" in css[brace + 1:limit]:
            context = re.sub(r"\s+", " ", prelude)
            index, depth = brace + 1, 1
            continue
        if not prelude and context and depth:
            index = brace + 1
            continue
        declarations = tuple(sorted(
            re.sub(r"\s+", " ", part).strip()
            for part in css[brace + 1:body_end].split(";") if part.strip()))
        found.append((context, re.sub(r"\s+", " ", prelude), declarations))
        index = body_end + 1
        if depth:
            closing = css.find("}", index)
            end = closing if closing != -1 else len(css)
            if css[index:end].strip() == "":
                index, context, depth = end + 1, "", 0
    return found


def _css_rule_map(css):
    """Return ``{(context, selector group): [declaration tuple, ...]}``."""
    grouped = {}
    for context, selector, declarations in _css_rules(css):
        grouped.setdefault((context, selector), []).append(declarations)
    return grouped


def _css_custom_properties(css):
    """Return ``{--name: value}`` for every custom property declared on ``:root``."""
    values = {}
    for _context, selector, declarations in _css_rules(css):
        if ":root" not in selector:
            continue
        for declaration in declarations:
            if declaration.startswith("--"):
                name, _sep, value = declaration.partition(":")
                values[name.strip()] = value.strip()
    return values


def test_the_deck_and_the_canonical_theme_declare_the_same_custom_properties():
    """A token that differs repaints the whole deck for a consumer of the reference copy."""
    deck = _css_custom_properties(_deck_inline_style())
    theme = _css_custom_properties(_read(DECK_THEME_PATH))

    assert sorted(deck) == sorted(theme), (
        "only in the deck: {0}; only in the theme: {1}".format(
            sorted(set(deck) - set(theme)), sorted(set(theme) - set(deck))))
    differing = dict((name, (deck[name], theme[name]))
                     for name in deck if deck[name] != theme[name])
    assert differing == {}, "custom properties whose values differ: {0}".format(differing)


def test_the_deck_and_the_canonical_theme_declare_the_same_selectors():
    """A selector present in one file and absent from the other is a degraded render."""
    deck = _css_rule_map(_deck_inline_style())
    theme = _css_rule_map(_read(DECK_THEME_PATH))

    assert sorted(set(deck) - set(theme)) == [], (
        "selectors only in the deck: {0}".format(sorted(set(deck) - set(theme))))
    assert sorted(set(theme) - set(deck)) == [], (
        "selectors only in the theme: {0}".format(sorted(set(theme) - set(deck))))


def test_every_selector_the_two_stylesheets_share_carries_the_same_declarations():
    """The defect QA found: one declaration differing, with nothing to notice it."""
    deck = _css_rule_map(_deck_inline_style())
    theme = _css_rule_map(_read(DECK_THEME_PATH))

    differing = [(key, deck[key], theme[key])
                 for key in sorted(set(deck) & set(theme)) if deck[key] != theme[key]]

    assert differing == [], (
        "selectors whose declarations differ between the deck and the canonical theme: "
        "{0}".format(differing))


def test_the_parity_census_the_matrix_publishes_is_the_stylesheets_own():
    """F70's 23 / 119 / 118 figures, re-derived rather than trusted."""
    deck_style = _deck_inline_style()
    stated = _stated(_read(MATRIX_PATH), DECK_PARITY_CENSUS_PATTERN)
    properties, blocks, groups = (int(number) for number in stated)

    assert properties == len(_css_custom_properties(deck_style))
    assert blocks == len(_css_rules(deck_style))
    assert groups == len(_css_rule_map(deck_style))


def test_the_deck_hides_the_stylesheet_mermaid_injects_from_the_accessibility_tree():
    """Without this the diagram slides announce the injected CSS ahead of their label."""
    deck = _read(DECK_PATH)

    assert "function hideRenderedInternals()" in deck
    assert "DIAGRAM_SELECTOR + ' svg style'" in deck
    assert "node.setAttribute('aria-hidden', 'true')" in deck
    assert "hideRenderedInternals();" in deck.split("function settleRender()")[1], (
        "settleRender does not hide the injected stylesheet, so a render leaves it exposed")


def test_the_deck_carries_a_content_landmark_and_names_every_table():
    """A landmark to jump to, and no table announced only as 'table'."""
    deck = _read(DECK_PATH)

    assert 'class="slides" role="main" aria-label=' in deck, (
        "the deck declares no content landmark")
    tables = re.findall(r"<table\b[^>]*>", deck)
    unnamed = [tag for tag in tables if "aria-label=" not in tag and "aria-labelledby=" not in tag]
    assert unnamed == [], "tables with no accessible name: {0}".format(unnamed)


def test_the_deck_controls_offer_a_large_enough_hit_target():
    """Reveal draws the cluster in `em`, so one font-size governs every control metric."""
    for css in (_deck_inline_style(), _read(DECK_THEME_PATH)):
        controls = _css_rule_map(css)[("", ".reveal .controls")]
        declared = [declaration for block in controls for declaration in block
                    if declaration.startswith("font-size:")]
        assert len(declared) == 1, (
            ".reveal .controls declares {0} font sizes".format(len(declared)))
        pixels = float(declared[0].split(":")[1].strip().rstrip("px"))
        assert pixels * 3.6 >= 44, (
            "an arrow at {0}em of {1}px is {2}px, below the 44px minimum".format(
                3.6, pixels, pixels * 3.6))


# --------------------------------------------------------------------------- #
# Link integrity of the documents this delivery authored, and the backlog      #
# entries that stand in for the links it may not repair                        #
# --------------------------------------------------------------------------- #

#: The four onboarding documents and the four Rule 1 and Rule 2 documents. Every relative link
#: in them has to resolve on disk, with the exception of the two the baseline README already
#: carried, declared below.
LINKED_DOCUMENTS = (
    "README.md",
    os.path.join("backend", "tests", "README.md"),
    os.path.join("frontend", "TESTING.md"),
    os.path.join("e2e", "README.md"),
    os.path.join("docs", "testing", "DECISION-LOG.md"),
    os.path.join("docs", "testing", "TRACEABILITY-MATRIX.md"),
    os.path.join("docs", "testing", "DASHBOARD-TEMPLATE.md"),
    os.path.join("docs", "testing", "SECURITY-GAPS.md"),
)

#: Parametrisation ids, because three of the eight are named ``README.md``.
LINKED_DOCUMENT_IDS = [path.replace(os.sep, "/") for path in LINKED_DOCUMENTS]

#: Relative link targets that legitimately do not resolve. Both are in the baseline README's
#: first hundred lines, which AAP 0.10.5 C3 makes additive-only, so this work records them
#: rather than repairing them. Each is paired with the phrase the suggested-next-tasks backlog
#: uses, and each is held to being genuinely absent - so the day either file appears, the
#: "still absent" leg fails and forces the backlog entry out with it.
BASELINE_DANGLING_LINKS = (
    ("README.md", "CONTRIBUTING.md", "links to a `CONTRIBUTING.md`"),
    ("README.md", "LICENSE", "line 93 to a `LICENSE`"),
)

#: Files the baseline README's setup and usage commands name and the repository does not
#: contain, each with the phrase the backlog uses. Same two-legged assertion as above.
BACKLOG_ABSENT_FILES = (
    ("requirements.txt", "pip install -r requirements.txt"),
    (".env.example", "cp .env.example .env"),
)

#: The placeholder origin the baseline README names in its clone command and its support
#: section. The backlog quotes it verbatim, so a corrected body and an uncorrected backlog
#: disagree and fail. The 404 itself is deliberately not asserted here: a test that reached
#: the network would be refused by the egress guard in ``tests/conftest.py``, by design.
README_PLACEHOLDER_ORIGIN = "https://github.com/your-org/code-skeptic-scanner"

#: The two findings about the deck rather than the application that section 7.8 of the
#: dashboard says are carried in the README's backlog. Asserted in both directions, so neither
#: document can claim the other records something it does not.
DECK_BACKLOG_ITEMS = ("text-transform: uppercase", "`complementary` landmark")

#: A markdown inline link, and the two spans a target may not be read out of: a backticked
#: code span and a fenced block. This tree's prose quotes regular expressions whose bracket
#: groups are indistinguishable from link syntax, so both exclusions are load-bearing rather
#: than tidy - without the fence exclusion, a Jest ``transform`` key reads as a broken link.
MARKDOWN_LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
MARKDOWN_CODE_SPAN = re.compile(r"`[^`\n]*`")
MARKDOWN_FENCE = re.compile(r"^\s*```")


def _relative_link_targets(relative):
    """Return ``[(line number, target), ...]`` for every resolvable-by-path link."""
    document = _read(os.path.join(REPOSITORY_ROOT, relative))
    targets, fenced = [], False
    for number, line in enumerate(document.split("\n"), 1):
        if MARKDOWN_FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        spans = [(match.start(), match.end())
                 for match in MARKDOWN_CODE_SPAN.finditer(line)]
        for match in MARKDOWN_LINK.finditer(line):
            if any(start <= match.start() < end for start, end in spans):
                continue
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            targets.append((number, target))
    return targets


def _unresolved_link_targets(relative):
    """Return the targets of ``relative`` that name nothing on disk."""
    base = os.path.dirname(os.path.join(REPOSITORY_ROOT, relative))
    unresolved = []
    for number, target in _relative_link_targets(relative):
        path = os.path.normpath(
            os.path.join(base, target.split("#")[0].split("?")[0]))
        if not os.path.exists(path):
            unresolved.append((number, target))
    return unresolved


@pytest.mark.parametrize("relative", LINKED_DOCUMENTS, ids=LINKED_DOCUMENT_IDS)
def test_every_relative_link_this_delivery_authored_resolves(relative):
    """A pointer to a file that is not there is the onboarding defect, not a typo."""
    declared = set(target for document, target, _phrase in BASELINE_DANGLING_LINKS
                   if document == relative)
    unresolved = _unresolved_link_targets(relative)
    undeclared = [entry for entry in unresolved if entry[1] not in declared]

    assert undeclared == [], (
        "{0} points at targets that do not exist and are not declared: {1}".format(
            relative, undeclared))


@pytest.mark.parametrize("document,target,phrase", BASELINE_DANGLING_LINKS,
                         ids=[entry[1] for entry in BASELINE_DANGLING_LINKS])
def test_every_declared_dangling_link_is_still_absent_and_still_recorded(
        document, target, phrase):
    """The exception is only legitimate while the file is absent and the backlog says so."""
    assert not os.path.exists(os.path.join(REPOSITORY_ROOT, target)), (
        "{0} now exists, so {1}'s link resolves and the backlog entry naming it is "
        "wrong".format(target, document))
    assert phrase in _read(os.path.join(REPOSITORY_ROOT, "README.md")), (
        "the backlog no longer records the absent {0}".format(target))


@pytest.mark.parametrize("target,phrase", BACKLOG_ABSENT_FILES,
                         ids=[entry[0] for entry in BACKLOG_ABSENT_FILES])
def test_the_backlog_records_every_absent_file_the_setup_commands_name(target, phrase):
    """A documented first step that cannot run is worth more as a backlog line than a note."""
    readme = _read(os.path.join(REPOSITORY_ROOT, "README.md"))
    present = [candidate for candidate in (target, os.path.join("backend", target))
               if os.path.exists(os.path.join(REPOSITORY_ROOT, candidate))]

    assert present == [], "{0} now exists at {1}; the backlog entry is stale".format(
        target, present)
    assert phrase in readme, "the README no longer quotes {0!r}".format(phrase)


def test_the_backlog_quotes_the_placeholder_origin_the_readme_still_carries():
    """If the body is ever corrected, the backlog entry has to go with it."""
    readme = _read(os.path.join(REPOSITORY_ROOT, "README.md"))
    lines = readme.split("\n")
    body = "\n".join(lines[:100])
    backlog = "\n".join(lines[100:])

    assert (README_PLACEHOLDER_ORIGIN in body) == (README_PLACEHOLDER_ORIGIN in backlog), (
        "the README body and its backlog disagree about the placeholder origin: body={0}, "
        "backlog={1}".format(
            README_PLACEHOLDER_ORIGIN in body, README_PLACEHOLDER_ORIGIN in backlog))


@pytest.mark.parametrize("item", DECK_BACKLOG_ITEMS)
def test_the_deck_findings_the_dashboard_defers_are_in_the_readme_backlog(item):
    """Section 7.8 says these are carried in the backlog; both directions are asserted."""
    assert item in _read(DASHBOARD_PATH), (
        "the dashboard no longer states the deck finding {0!r}".format(item))
    assert item in _read(os.path.join(REPOSITORY_ROOT, "README.md")), (
        "the dashboard defers {0!r} to the README backlog, which does not carry it".format(
            item))


# --------------------------------------------------------------------------- #
# The QA-finding disposition register, and this module's own published size    #
# --------------------------------------------------------------------------- #

#: Every finding id the final-acceptance pass raised. The register has to carry all of them:
#: a decline recorded only in aggregate is indistinguishable, later, from one nobody read.
QA_FINDING_IDS = tuple("QA-{0:02d}".format(number) for number in range(1, 33))

#: The three dispositions a register row may carry, each with the phrasing the register's own
#: prose publishes its tally as. The tallies are re-derived from the rows, never trusted.
QA_DISPOSITION_PATTERNS = (
    ("Declined", r"\*\*(\d+) declined\*\*"),
    ("Resolved", r"\*\*(\d+) resolved\*\*"),
    ("Documented", r"\*\*(\d+)\*\* not defects of"),
)

#: How ``TRACEABILITY-MATRIX.md`` publishes the size of an infrastructure suite, and which row
#: publishes which. Both figures this checkpoint looked at were wrong: F102's went stale the
#: moment a case was added to the module it describes, and F101's had been contradicted by
#: ``backend/tests/README.md`` for a whole checkpoint. That is the same defect class as every
#: other figure corrected here, so all four are bound rather than restated. Each figure is
#: looked up inside its own row rather than anchored to a phrase, so extending a row's prose
#: cannot silently unbind it - which is exactly what the first attempt at this check did.
MATRIX_SUITE_CASE_COUNTS = (
    ("F76", os.path.join("backend", "tests", "test_dependency_closure.py")),
    ("F91", os.path.join("backend", "tests", "test_coverage_gate.py")),
    ("F101", os.path.join("backend", "tests", "test_dashboard_extract.py")),
    ("F102", os.path.join("backend", "tests", "test_docs_contract.py")),
)

#: The one phrasing every such figure uses, asserted unique within the row that carries it.
CASE_COUNT_PATTERN = r"(\d+) cases"


def _qa_disposition_register():
    """Return ``{finding: (severity, reported, disposition, clause, carried)}`` from the log."""
    pattern = (r"^\|\s*(QA-\d{2})\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$")
    rows = {}
    for line in _read(DECISION_LOG_PATH).split("\n"):
        match = re.match(pattern, line)
        if match:
            assert match.group(1) not in rows, (
                "the register repeats {0}".format(match.group(1)))
            rows[match.group(1)] = tuple(cell.strip() for cell in match.groups()[1:])
    return rows


def test_the_disposition_register_carries_every_finding_exactly_once():
    """All 32, or the register is a selection rather than a register."""
    rows = _qa_disposition_register()

    assert sorted(rows) == sorted(QA_FINDING_IDS), (
        "missing: {0}; unexpected: {1}".format(
            sorted(set(QA_FINDING_IDS) - set(rows)), sorted(set(rows) - set(QA_FINDING_IDS))))


@pytest.mark.parametrize("finding", QA_FINDING_IDS)
def test_every_disposition_row_states_a_clause_and_a_pointer(finding):
    """A disposition with no reason and nowhere to follow is what D324 refused to allow."""
    rows = _qa_disposition_register()
    assert finding in rows, "the register has no row for {0}".format(finding)
    _severity, reported, disposition, clause, carried = rows[finding]

    assert reported, "{0} states no finding".format(finding)
    assert disposition in [name for name, _pattern in QA_DISPOSITION_PATTERNS], (
        "{0} carries an unknown disposition {1!r}".format(finding, disposition))
    assert clause, "{0} states no clause".format(finding)
    assert carried, "{0} points nowhere".format(finding)

    if disposition == "Declined":
        assert "\u00a7" in clause, (
            "{0} is declined without citing a clause of the plan: {1!r}".format(
                finding, clause))
    else:
        assert _cited_rows(clause + " " + carried), (
            "{0} is {1} without citing the decision row that says so".format(
                finding, disposition.lower()))


def test_the_disposition_counts_the_register_publishes_are_its_own():
    """The three tallies, re-derived from the rows rather than read from the prose."""
    dispositions = [row[2] for row in _qa_disposition_register().values()]
    log = _read(DECISION_LOG_PATH)

    for name, pattern in QA_DISPOSITION_PATTERNS:
        stated = int(_stated(log, pattern))
        assert stated == dispositions.count(name), (
            "the register publishes {0} {1} rows and carries {2}".format(
                stated, name.lower(), dispositions.count(name)))
    assert len(dispositions) == len(QA_FINDING_IDS)


@pytest.mark.parametrize("row,relative", MATRIX_SUITE_CASE_COUNTS)
def test_the_case_count_the_matrix_states_for_a_suite_is_the_sessions_own(request, row,
                                                                         relative):
    """The matrix says how many cases a suite has; the running session is asked, not the prose.

    A run that deselects within a file cannot answer the question, so the three ways of doing
    that - ``-k``, ``-m`` and an explicit node id - stand the check down rather than fail it,
    and a run that never collected the file in question stands that row down on its own. A full
    run of the suite therefore answers all four rows, and a run of this file alone answers F102.
    Under ``-n auto`` each worker performs the whole collection before running its slice, so
    the count a worker sees is the same one a serial run sees.
    """
    filtered = (bool(request.config.option.keyword)
                or bool(request.config.option.markexpr)
                or any("::" in argument for argument in request.config.args))
    if filtered:
        return

    target = os.path.join(REPOSITORY_ROOT, relative)
    collected = [item for item in request.session.items if str(item.path) == target]
    if not collected:
        return

    _artifact, covers = _matrix_rows()[row]
    found = re.findall(CASE_COUNT_PATTERN, covers)
    assert len(found) == 1, "{0} states {1} case counts, not one".format(row, len(found))

    assert int(found[0]) == len(collected), (
        "{0} states {1} cases for {2}; the session collects {3}".format(
            row, found[0], relative.replace(os.sep, "/"), len(collected)))


# --------------------------------------------------------------------------- #
# Byte hygiene of the artifacts this delivery authored                         #
# --------------------------------------------------------------------------- #

#: Every prose or markup artifact this delivery authored, plus the canonical stylesheet the
#: deck is kept in parity with. These are the files a reader reads, so a byte-level defect in
#: one of them is a defect in the deliverable rather than in a working copy.
BYTE_HYGIENE_ARTIFACTS = CITING_DOCUMENTS + (
    os.path.join("blitzy-deck", "references", "blitzy-reveal-theme.css"),
)

#: What a UTF-8 em-dash becomes when an editor reads the file as a single-byte codepage and
#: writes it back as UTF-8. A single occurrence means a tool round-tripped the file wrongly -
#: which happened to two of these documents during this delivery and had to be reverted.
MOJIBAKE_EM_DASH = b"\xc3\xa2\xe2\x82\xac\xe2\x80\x9d"

#: Control bytes none of these artifacts has any reason to carry. Tab, line feed and carriage
#: return are excluded, because those are the file's own structure rather than content.
FORBIDDEN_CONTROL_BYTES = tuple(
    list(range(0, 9)) + [11, 12] + list(range(14, 32)))


@pytest.mark.parametrize("relative", BYTE_HYGIENE_ARTIFACTS)
def test_every_authored_artifact_is_clean_utf8_with_uniform_line_endings(relative):
    """No mojibake, no control byte, no stray carriage return, no mixed line endings.

    Every defect this asserts against was met for real while these documents were written. An
    editor that read two of them as a single-byte codepage rewrote every pre-existing em-dash
    as its double-encoded form, and a section appender left 51 doubled carriage returns in
    ``DECISION-LOG.md`` - invisible to a reader, but enough for git to classify the file as
    binary and render a one-line change as a 1,575-line rewrite, which is how a review stops
    being able to see what changed. A stray 0x08 in the same file had eaten a letter outright.

    Line endings are asserted uniform rather than fixed to one convention, because the same
    tree is checked out with CRLF on Windows and LF elsewhere; mixing the two within one file
    is the defect, not either choice.
    """
    with io.open(os.path.join(REPOSITORY_ROOT, relative), "rb") as handle:
        raw = handle.read()

    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AssertionError("{0} is not valid UTF-8: {1}".format(relative, error))

    assert raw.count(MOJIBAKE_EM_DASH) == 0, (
        "{0} carries {1} double-encoded em-dash(es): an editor round-tripped it through a "
        "single-byte codepage".format(relative, raw.count(MOJIBAKE_EM_DASH)))

    present = sorted(value for value in FORBIDDEN_CONTROL_BYTES if value in bytearray(raw))
    assert present == [], "{0} carries control byte(s) {1}".format(
        relative, ["0x{0:02x}".format(value) for value in present])

    stray = raw.replace(b"\r\n", b"").count(b"\r")
    assert stray == 0, (
        "{0} carries {1} carriage return(s) that do not end a line".format(relative, stray))

    lines = raw.split(b"\n")[:-1]
    with_cr = sum(1 for line in lines if line.endswith(b"\r"))
    assert with_cr in (0, len(lines)), (
        "{0} mixes line endings: {1} of {2} lines end CRLF".format(
            relative, with_cr, len(lines)))

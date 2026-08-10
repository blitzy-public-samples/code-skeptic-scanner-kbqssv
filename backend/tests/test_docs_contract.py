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

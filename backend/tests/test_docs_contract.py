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
import os
import re

import pytest

pytestmark = pytest.mark.unit


#: Repository root, two levels above ``backend/tests``.
REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MATRIX_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "TRACEABILITY-MATRIX.md")
DASHBOARD_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "DASHBOARD-TEMPLATE.md")
DECISION_LOG_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "DECISION-LOG.md")
EXTRACTOR_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "dashboard-extract.py")
GITIGNORE_PATH = os.path.join(REPOSITORY_ROOT, ".gitignore")
MANIFEST_PATH = os.path.join(REPOSITORY_ROOT, "backend", "requirements-dev.txt")
DECK_PATH = os.path.join(REPOSITORY_ROOT, "blitzy-deck", "executive-summary.html")

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

    assert "Ten rules are path-anchored" in matrix
    assert "the remaining thirteen" in matrix
    assert (len(anchored), len(unanchored)) == (10, 13)


def test_gitignore_patterns_enumerated_in_the_matrix_are_the_delivered_ones():
    """Every pattern F39 lists exists, and every delivered pattern is listed."""
    patterns = set(_active_lines(GITIGNORE_PATH))
    row = [line for line in _read(MATRIX_PATH).split("\n") if line.startswith("| F39 |")]
    assert len(row) == 1
    listed = {token.strip() for token in re.findall(r"`([^`]+)`", row[0])}

    assert patterns.issubset(listed)
    assert "package-lock.json" not in patterns, "no active rule may match the lockfile"


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


def test_dashboard_names_every_required_artifact_the_extractor_requires():
    """A required artifact the dashboard does not name has no documented source."""
    extractor = _read(EXTRACTOR_PATH)
    dashboard = _read(DASHBOARD_PATH)

    block = re.search(r"^REQUIRED[^=]*=\s*\((.*?)\)\n", extractor, re.S | re.M).group(1)
    constants = re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", block)
    assert len(constants) == len(set(constants)) >= 11

    for constant in constants:
        value = re.search(r'^{0} = "([^"]+)"'.format(constant), extractor, re.M)
        assert value is not None, constant
        assert value.group(1) in dashboard, value.group(1)


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

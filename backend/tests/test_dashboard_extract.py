"""Contract tests for ``docs/testing/dashboard-extract.py``.

Subject
-------
The producer of ``docs/testing/DASHBOARD-TEMPLATE.md``. Nothing else in this
repository turns a run into a published figure, so a defect here is a defect in
every number the dashboard carries, and two of its properties are invisible in a
successful run:

The artifact contract has to be complete
    ``--require-all`` exists so a missing artifact is fatal rather than rendered
    as an empty cell. An artifact the extractor *reads* but does not *require* is
    the one case that exit status cannot catch: the run succeeds and the panels it
    feeds come out blank.

A gate figure has to be the figure the runner fails on
    Jest declares one ``coverageThreshold`` group per path, so gate G2 is twelve
    independent comparisons. A figure computed over the three packages combined
    can sit above the threshold while one package sits below it, which would
    publish a pass for a run Jest fails.

A partial result stream has to be refused, not published
    ``backend/pytest.ini`` carries ``--junitxml`` in ``addopts``, so every pytest
    invocation writes the canonical stream -- including a single-file or ``-k``
    filtered run. The zero-case refusal cannot see that case, because a partial
    run leaves a non-zero count, and a non-zero count reads to every consumer
    exactly like a full one. The collected count in the readiness artifact is the
    independent witness, so the two are compared.

    All three runners behave this way: ``frontend/jest.config.js`` declares the
    ``jest-junit`` reporter and ``e2e/playwright.config.ts`` declares the ``junit``
    one, so a single-file Jest run and a single-spec Playwright run overwrite their
    layer's stream as readily as a filtered pytest run overwrites the backend's.
    Each comparison is therefore made against that layer's own witness, and the
    cases below cover all three.

Scope
-----
This module imports no ``app`` module and reads no committed artifact: every case
builds the artifacts it needs under ``tmp_path`` and points the extractor's path
constants at them, so a case is unaffected by whether a suite has been run. It
sits at the ``tests/`` root beside the other suite-level gates rather than under
``unit/``, whose subjects are production modules.

The extractor is loaded from its path rather than imported, because its filename
carries a hyphen and it lives outside ``backend/``.

@see docs/testing/DASHBOARD-TEMPLATE.md - the panels the extractor fills.
@see docs/testing/DECISION-LOG.md - rows D253, D332 and D333.
"""

import importlib.util
import io
import json
import os
import sys

import pytest

pytestmark = pytest.mark.unit


#: Repository root, two levels above ``backend/tests``.
REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: The extractor's path, relative to :data:`REPOSITORY_ROOT`.
EXTRACTOR_PATH = os.path.join(REPOSITORY_ROOT, "docs", "testing", "dashboard-extract.py")

#: Threshold every gated frontend package is held to, in percent.
GATE_THRESHOLD = 80.0


def _load_extractor():
    """Load the extractor as a module object, without importing it by name."""
    spec = importlib.util.spec_from_file_location("blitzy_dashboard_extract", EXTRACTOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: One shared instance: the module holds only constants and pure functions, and
#: every case redirects the path constants it needs through ``monkeypatch``.
extractor = _load_extractor()


def _write(path, text):
    """Write ``text`` to ``path``, creating parent directories."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _metric(covered, total):
    """One Istanbul metric block, with the percentage the artifact reports."""
    pct = "Unknown" if total == 0 else covered * 100.0 / total
    return {"total": total, "covered": covered, "skipped": 0, "pct": pct}


def _file_entry(covered, total):
    """One ``coverage-summary.json`` file entry, identical across all four metrics."""
    return {metric: _metric(covered, total) for metric in extractor.METRICS}


def coverage_summary(store, schema, services):
    """A ``coverage-summary.json`` payload with one file per gated package.

    :param store: ``(covered, total)`` for ``src/store``.
    :param schema: ``(covered, total)`` for ``src/schema``.
    :param services: ``(covered, total)`` for ``src/services``.
    """
    files = {
        "/repo/frontend/src/store/tweetSlice.ts": _file_entry(*store),
        "/repo/frontend/src/schema/tweetSchema.ts": _file_entry(*schema),
        "/repo/frontend/src/services/api.ts": _file_entry(*services),
    }
    covered = sum(pair[0] for pair in (store, schema, services))
    total = sum(pair[1] for pair in (store, schema, services))
    payload = dict(files)
    payload["total"] = _file_entry(covered, total)
    return json.dumps(payload)


#: A usable lcov artifact: one source record carrying one uncovered line.
USABLE_LCOV = "TN:\nSF:/repo/frontend/src/store/tweetSlice.ts\nDA:11,0\nDA:12,3\nend_of_record\n"

def backend_junit(tests, skipped=0):
    """A pytest ``xunit2`` stream declaring ``tests`` cases, ``skipped`` of them skipped."""
    cases = []
    for number in range(tests):
        state = "<skipped message=\"reasoned\" />" if number < skipped else ""
        cases.append(
            '<testcase classname="tests.unit.test_subject" name="test_case_{0}" '
            'time="0.001">{1}</testcase>'.format(number, state))
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites name="pytest tests">'
        '<testsuite name="pytest" errors="0" failures="0" skipped="{0}" tests="{1}" '
        'time="1.000">{2}</testsuite>'
        "</testsuites>".format(skipped, tests, "".join(cases))
    )


def collect_only(collected):
    """The tail of a retained ``pytest --collect-only -q`` run."""
    return (
        "tests/unit/test_subject.py::test_case_0\n"
        "\n"
        "{0} tests collected in 1.79s\n".format(collected)
    )


#: The summary a name-filtered Jest run prints when every module loaded.
READY_SUMMARY = (
    "Test Suites: 24 skipped, 0 of 24 total\n"
    "Tests:       370 skipped, 370 total\n"
    "Snapshots:   0 total\n"
    "Time:        12.14 s\n"
    'Ran all test suites with tests matching "__readiness_probe_that_matches_no_test__".\n'
)

#: The same summary when one module threw while loading.
BROKEN_SUMMARY = (
    "Test Suites: 1 failed, 24 skipped, 1 of 25 total\n"
    "Tests:       370 skipped, 370 total\n"
)


# --------------------------------------------------------------------------- #
# The artifact contract.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "constant",
    [
        "BACKEND_COVERAGE_XML",
        "BACKEND_COVERAGE_JSON",
        "BACKEND_JUNIT",
        "BACKEND_COLLECT_ONLY",
        "FRONTEND_COVERAGE_SUMMARY",
        "FRONTEND_LCOV",
        "FRONTEND_JUNIT",
        "FRONTEND_LIST_TESTS",
        "FRONTEND_READINESS",
        "E2E_JUNIT",
        "E2E_LIST_TESTS",
    ],
)
def test_every_artifact_the_extractor_reads_is_required(constant):
    """`--require-all` covers each artifact a panel is built from."""
    assert getattr(extractor, constant) in extractor.REQUIRED


def test_the_required_contract_names_no_artifact_twice():
    """A duplicate would report the same absence twice and hide a missing entry."""
    assert len(set(extractor.REQUIRED)) == len(extractor.REQUIRED)


def test_require_all_fails_when_the_uncovered_line_source_is_absent(tmp_path, monkeypatch):
    """The one artifact whose absence used to leave `--require-all` at exit 0."""
    monkeypatch.setattr(extractor, "FRONTEND_LCOV", str(tmp_path / "absent-lcov.info"))
    monkeypatch.setattr(extractor, "REQUIRED", (extractor.FRONTEND_LCOV,))

    assert extractor.lcov_is_usable() is False
    assert extractor.main(["--require-all", "--json"]) == 1


def test_require_all_fails_when_the_uncovered_line_source_carries_no_records(
    tmp_path, monkeypatch
):
    """Present is not usable: an lcov with no `SF:`/`DA:` pair measures nothing."""
    empty = _write(str(tmp_path / "coverage" / "lcov.info"), "TN:\nend_of_record\n")
    monkeypatch.setattr(extractor, "FRONTEND_LCOV", empty)
    monkeypatch.setattr(extractor, "REQUIRED", (empty,))

    assert os.path.isfile(empty)
    assert extractor.lcov_is_usable() is False
    assert extractor.main(["--require-all", "--json"]) == 1


def test_a_populated_uncovered_line_source_is_usable(tmp_path, monkeypatch):
    """The positive case, so the check above cannot pass by always refusing."""
    populated = _write(str(tmp_path / "coverage" / "lcov.info"), USABLE_LCOV)
    monkeypatch.setattr(extractor, "FRONTEND_LCOV", populated)

    assert extractor.lcov_is_usable() is True
    assert extractor._lcov_uncovered() == {
        "/repo/frontend/src/store/tweetSlice.ts": [11]
    }


# --------------------------------------------------------------------------- #
# Gate G2 semantics: twelve independent comparisons, not one over their sum.
# --------------------------------------------------------------------------- #


def _frontend_coverage(tmp_path, monkeypatch, summary):
    """Parse a synthetic ``coverage-summary.json`` through the extractor."""
    written = _write(str(tmp_path / "coverage" / "coverage-summary.json"), summary)
    monkeypatch.setattr(extractor, "FRONTEND_COVERAGE_SUMMARY", written)
    monkeypatch.setattr(extractor, "FRONTEND_LCOV", str(tmp_path / "absent.info"))
    return extractor.frontend_coverage()


def test_the_gate_is_one_comparison_per_package_and_metric(tmp_path, monkeypatch):
    """Three `coverageThreshold` groups times four metrics is twelve gates."""
    coverage = _frontend_coverage(
        tmp_path, monkeypatch, coverage_summary((9, 10), (10, 10), (10, 10))
    )
    rows = extractor.gated_frontend_percentages(coverage)

    assert len(rows) == len(extractor.GATED_FRONTEND_PACKAGES) * len(extractor.METRICS)
    assert {prefix for prefix, _, _ in rows} == set(extractor.GATED_FRONTEND_PACKAGES)
    assert {metric for _, metric, _ in rows} == set(extractor.METRICS)


def test_a_failing_package_is_not_hidden_by_two_stronger_packages(tmp_path, monkeypatch):
    """The defect this figure existed to publish, stated as an oracle.

    ``src/store`` at 70% fails its own threshold group, so Jest fails the run.
    Summed with two packages at 100% the combined figure is 98.57%, which is what
    a single aggregate comparison would have published as a pass.
    """
    coverage = _frontend_coverage(
        tmp_path, monkeypatch, coverage_summary((7, 10), (100, 100), (100, 100))
    )

    combined_covered = 7 + 100 + 100
    combined_total = 10 + 100 + 100
    combined = extractor.pct_frontend(combined_covered, combined_total)
    assert combined is not None and combined >= GATE_THRESHOLD

    worst = extractor.gated_frontend_worst(coverage)
    assert worst == pytest.approx(70.0)
    assert worst < GATE_THRESHOLD

    failing = [(prefix, metric) for prefix, metric, pct
               in extractor.gated_frontend_percentages(coverage)
               if pct is not None and pct < GATE_THRESHOLD]
    assert sorted(failing) == sorted(
        [("src/store", metric) for metric in extractor.METRICS]
    )


def test_the_worst_gate_is_reported_when_every_package_passes(tmp_path, monkeypatch):
    """A passing run reports its narrowest margin rather than an average."""
    coverage = _frontend_coverage(
        tmp_path, monkeypatch, coverage_summary((81, 100), (95, 100), (100, 100))
    )

    assert extractor.gated_frontend_worst(coverage) == pytest.approx(81.0)


def test_the_worst_gate_is_unknown_without_a_coverage_summary():
    """No artifact means no figure, never a zero that reads as a measurement."""
    assert extractor.gated_frontend_percentages({"available": False}) == []
    assert extractor.gated_frontend_worst({"available": False}) is None


def test_the_trend_follows_the_worst_gate(tmp_path, monkeypatch):
    """`collect()` publishes the same figure the gate fails on."""
    summary = _write(
        str(tmp_path / "coverage" / "coverage-summary.json"),
        coverage_summary((7, 10), (100, 100), (100, 100)),
    )
    monkeypatch.setattr(extractor, "FRONTEND_COVERAGE_SUMMARY", summary)
    for constant in ("BACKEND_COVERAGE_XML", "BACKEND_COVERAGE_JSON", "BACKEND_JUNIT",
                     "BACKEND_COLLECT_ONLY", "FRONTEND_LCOV", "FRONTEND_JUNIT",
                     "FRONTEND_LIST_TESTS", "FRONTEND_READINESS", "E2E_JUNIT",
                     "E2E_LIST_TESTS", "E2E_TEST_RESULTS"):
        monkeypatch.setattr(extractor, constant, str(tmp_path / ("absent-" + constant)))

    assert extractor.collect()["trend"]["K2"] == pytest.approx(70.0)


# --------------------------------------------------------------------------- #
# Frontend readiness: loaded and transformed, not merely discovered.
# --------------------------------------------------------------------------- #


def test_readiness_reports_every_module_that_loaded(tmp_path):
    """A green readiness run names the module count and runs no test body."""
    path = _write(str(tmp_path / "reports" / "readiness.txt"), READY_SUMMARY)
    result = extractor.jest_readiness(path)

    assert result["available"] is True
    assert result["count"] == 24
    assert result["errors"] == 0
    assert result["declared_tests"] == 370
    assert result["executed_tests"] == 0


def test_readiness_is_unusable_when_a_module_failed_to_load(tmp_path):
    """The property `--listTests` cannot report, because it resolves no import."""
    path = _write(str(tmp_path / "reports" / "readiness.txt"), BROKEN_SUMMARY)
    result = extractor.jest_readiness(path)

    assert result["available"] is False
    assert "1 of 25 test modules failed to load or transform" in result["reason"]


def test_readiness_is_unusable_when_the_output_is_not_a_jest_summary(tmp_path):
    """A `--listTests` listing pasted here is refused rather than counted."""
    path = _write(
        str(tmp_path / "reports" / "readiness.txt"),
        "/repo/frontend/src/store/tweetSlice.test.ts\n",
    )
    result = extractor.jest_readiness(path)

    assert result["available"] is False
    assert "no Jest 'Test Suites:' summary" in result["reason"]


def test_readiness_is_unavailable_when_the_artifact_was_never_produced(tmp_path):
    """Absent is reported as absent, with the path named."""
    path = str(tmp_path / "reports" / "readiness.txt")
    result = extractor.jest_readiness(path)

    assert result["available"] is False
    assert result["source"] == path


def test_require_all_fails_when_readiness_reports_a_failed_module(tmp_path, monkeypatch):
    """A readiness artifact that exists and records a failure is still fatal."""
    broken = _write(str(tmp_path / "reports" / "readiness.txt"), BROKEN_SUMMARY)
    lcov = _write(str(tmp_path / "coverage" / "lcov.info"), USABLE_LCOV)
    monkeypatch.setattr(extractor, "FRONTEND_READINESS", broken)
    monkeypatch.setattr(extractor, "FRONTEND_LCOV", lcov)
    monkeypatch.setattr(extractor, "REQUIRED", (broken, lcov))

    assert extractor.main(["--require-all", "--json"]) == 1


# --------------------------------------------------------------------------- #
# A partial backend result stream: refused against the collected count.
# --------------------------------------------------------------------------- #


#: Path constants redirected to non-existent files, so a case reads only what it wrote.
ISOLATED_CONSTANTS = (
    "BACKEND_COVERAGE_XML", "BACKEND_COVERAGE_JSON", "BACKEND_COVERAGE_GATE",
    "FRONTEND_COVERAGE_SUMMARY", "FRONTEND_LCOV", "FRONTEND_JUNIT",
    "FRONTEND_LIST_TESTS", "FRONTEND_READINESS", "E2E_JUNIT", "E2E_LIST_TESTS",
    "E2E_BROWSER", "E2E_TEST_RESULTS",
)


def _backend_only(tmp_path, monkeypatch, declared, collected, skipped=0):
    """Point the extractor at one synthetic backend stream and readiness output."""
    stream = _write(str(tmp_path / "reports" / "junit.xml"),
                    backend_junit(declared, skipped=skipped))
    readiness = _write(str(tmp_path / "reports" / "collect-only.txt"),
                       collect_only(collected))
    monkeypatch.setattr(extractor, "BACKEND_JUNIT", stream)
    monkeypatch.setattr(extractor, "BACKEND_COLLECT_ONLY", readiness)
    for constant in ISOLATED_CONSTANTS:
        monkeypatch.setattr(extractor, constant, str(tmp_path / ("absent-" + constant)))
    monkeypatch.setattr(extractor, "REQUIRED", (stream, readiness))
    return stream, readiness


def test_a_partial_backend_stream_is_withdrawn_rather_than_published(tmp_path, monkeypatch):
    """The case the zero-case refusal cannot see: 405 cases where 1015 were collected."""
    stream, _readiness = _backend_only(tmp_path, monkeypatch, declared=405, collected=1015)

    data = extractor.collect()

    assert data["backend_junit"]["available"] is False
    assert data["backend_junit"]["source"] == stream
    assert "declares 405 test cases while collection found 1015" in (
        data["backend_junit"]["reason"])
    assert data["backend_partial_stream"] is not None
    # Nothing downstream may carry the partial figure.
    assert data["trend"]["tests"] == 0


def test_a_partial_backend_stream_is_named_on_stderr_and_is_fatal(
    tmp_path, monkeypatch, capsys
):
    """A stream that parses, declares cases and is still wrong is reported and fatal."""
    _backend_only(tmp_path, monkeypatch, declared=405, collected=1015)

    status = extractor.main(["--require-all", "--json"])
    reported = capsys.readouterr().err

    assert status == 1
    assert "artifact unusable: backend result stream" in reported
    assert "declares 405 test cases while collection found 1015" in reported


def test_a_complete_backend_stream_is_accepted(tmp_path, monkeypatch, capsys):
    """The positive case, so the refusal above cannot pass by always refusing."""
    _backend_only(tmp_path, monkeypatch, declared=1015, collected=1015, skipped=3)

    data = extractor.collect()
    extractor.main(["--require-all", "--json"])
    reported = capsys.readouterr().err

    assert data["backend_junit"]["available"] is True
    assert data["backend_junit"]["tests"] == 1015
    assert data["backend_junit"]["skipped"] == 3
    assert data["backend_junit"]["passed"] == 1012
    assert data["backend_partial_stream"] is None
    assert data["trend"]["tests"] == 1015
    assert "backend result stream" not in reported


def test_the_mismatch_is_reported_as_a_failed_readiness_row(tmp_path, monkeypatch):
    """6.4 states what went wrong, rather than falling back to "not produced"."""
    _backend_only(tmp_path, monkeypatch, declared=405, collected=1015)

    rendered = extractor.render(extractor.collect())

    row = [line for line in rendered.split("\n")
           if line.startswith("| Backend tests collected |")]
    assert len(row) == 1
    assert "declares 405 test cases while collection found 1015" in row[0]
    assert row[0].rstrip().endswith("| FAIL |")


def test_no_comparison_is_made_without_a_collected_count():
    """An absent readiness artifact leaves the stream as it was, not refused."""
    stream = {"available": True, "tests": 405}

    assert extractor.partial_stream_reason(stream, None) is None
    assert extractor.partial_stream_reason({"available": False}, 1015) is None


# --------------------------------------------------------------------------- #
# A filtered frontend result stream: refused on the reason its skips carry.
#
# The comparison above cannot see this one. A Jest name filter does not drop the
# tests it excludes - it registers every identity and re-classifies the excluded
# ones as skipped - so the root case count still declares the whole suite and
# equals every witness a readiness artifact could offer. What discriminates is
# that a deliberate skip in this suite states its reason in its own title.
# --------------------------------------------------------------------------- #


def jest_junit(passed, reasoned_skips=0, filtered_skips=0):
    """A ``jest-junit`` stream whose skips carry, or do not carry, a reason.

    :param passed: cases reported as passing.
    :param reasoned_skips: skipped cases whose name carries the ``BLOCKED:`` marker,
        as an ``it.skip`` in this suite does.
    :param filtered_skips: skipped cases whose name does not, as a ``-t`` filtered
        run produces.
    """
    cases = []
    for number in range(passed):
        cases.append('<testcase classname="src/utils/formatUtils.test.ts" '
                     'name="formatNumber case {0}" time="0.001" />'.format(number))
    for number in range(reasoned_skips):
        cases.append(
            '<testcase classname="src/pages/Dashboard.test.tsx" '
            'name="pages/Dashboard renders case {0} - BLOCKED: src/store/index.ts '
            'exports no useAppDispatch" time="0"><skipped /></testcase>'.format(number))
    for number in range(filtered_skips):
        cases.append('<testcase classname="src/store/tweetSlice.test.ts" '
                     'name="tweetSlice reducer case {0}" time="0">'
                     "<skipped /></testcase>".format(number))
    total = passed + reasoned_skips + filtered_skips
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<testsuites name="jest tests" tests="{total}" failures="0" errors="0" '
        'time="1.000">'
        '<testsuite name="suite" errors="0" failures="0" skipped="{skipped}" '
        'tests="{total}" time="1.000">{cases}</testsuite>'
        "</testsuites>".format(total=total, skipped=reasoned_skips + filtered_skips,
                               cases="".join(cases))
    )


#: Path constants redirected away for a frontend-only case, so it reads only what it wrote.
FRONTEND_ISOLATED_CONSTANTS = tuple(
    name for name in ISOLATED_CONSTANTS if name != "FRONTEND_JUNIT"
) + ("BACKEND_JUNIT", "BACKEND_COLLECT_ONLY")


def _frontend_only(tmp_path, monkeypatch, passed, reasoned_skips=0, filtered_skips=0):
    """Point the extractor at one synthetic frontend stream and nothing else."""
    stream = _write(str(tmp_path / "reports" / "jest-junit.xml"),
                    jest_junit(passed, reasoned_skips, filtered_skips))
    monkeypatch.setattr(extractor, "FRONTEND_JUNIT", stream)
    for constant in FRONTEND_ISOLATED_CONSTANTS:
        monkeypatch.setattr(extractor, constant, str(tmp_path / ("absent-" + constant)))
    monkeypatch.setattr(extractor, "REQUIRED", (stream,))
    return stream


def test_a_filtered_frontend_stream_is_withdrawn_rather_than_published(
    tmp_path, monkeypatch
):
    """The case a count comparison cannot see: 300 skipped, 24 of them reasoned."""
    stream = _frontend_only(tmp_path, monkeypatch, passed=71, reasoned_skips=24,
                            filtered_skips=276)

    data = extractor.collect()

    assert data["frontend_junit"]["available"] is False
    assert data["frontend_junit"]["source"] == stream
    assert "declares 300 skipped cases of which 276 state no 'BLOCKED:' reason" in (
        data["frontend_junit"]["reason"])
    assert data["frontend_unreasoned_skips"] is not None
    # Nothing downstream may carry the filtered figures.
    assert data["trend"]["tests"] == 0
    assert data["trend"]["skipped"] == 0


def test_a_filtered_frontend_stream_is_named_on_stderr_and_is_fatal(
    tmp_path, monkeypatch, capsys
):
    """It parses, declares the full case count, and is still refused and reported."""
    _frontend_only(tmp_path, monkeypatch, passed=71, reasoned_skips=24,
                   filtered_skips=276)

    status = extractor.main(["--require-all", "--json"])
    reported = capsys.readouterr().err

    assert status == 1
    assert "artifact unusable: frontend result stream" in reported
    assert "state no 'BLOCKED:' reason" in reported


def test_a_frontend_stream_whose_every_skip_is_reasoned_is_accepted(
    tmp_path, monkeypatch
):
    """The positive case, so the refusal above cannot pass by always refusing."""
    _frontend_only(tmp_path, monkeypatch, passed=347, reasoned_skips=24)

    data = extractor.collect()

    assert data["frontend_junit"]["available"] is True
    assert data["frontend_junit"]["tests"] == 371
    assert data["frontend_junit"]["skipped"] == 24
    assert data["frontend_junit"]["passed"] == 347
    assert data["frontend_unreasoned_skips"] is None
    assert data["trend"]["tests"] == 371


def test_a_frontend_stream_with_no_skip_at_all_is_accepted(tmp_path, monkeypatch):
    """A suite that resolves every blocker must not be read as a filtered run."""
    _frontend_only(tmp_path, monkeypatch, passed=371)

    data = extractor.collect()

    assert data["frontend_junit"]["available"] is True
    assert data["frontend_junit"]["skipped"] == 0
    assert data["frontend_unreasoned_skips"] is None


def test_an_unavailable_frontend_stream_is_left_as_it_was():
    """An absent or unparseable stream is already reported; it is not re-refused."""
    assert extractor.unreasoned_skip_reason({"available": False}) is None
    assert extractor.unreasoned_skip_reason(
        {"available": True, "skips": []}) is None

# --------------------------------------------------------------------------- #
# The same refusal for the other two streams, each against its own witness.
# --------------------------------------------------------------------------- #


#: Per-layer parametrisation of the same contract: the layer, which label ``main`` reports
#: it under, how the message names that layer's witness, and which readiness row of section
#: 6.4 has to state the reason instead of falling back to "not produced".
PARTIAL_LAYERS = (
    ("frontend", "frontend result stream", "the readiness probe registered",
     "| Frontend test identities registered equal the frontend total in 6.3 |"),
    ("e2e", "end-to-end result stream", "discovery found",
     "| E2E tests discovered |"),
)

#: Short parametrisation ids, so a case name states the layer under test.
PARTIAL_LAYER_IDS = [layer[0] for layer in PARTIAL_LAYERS]


def frontend_junit(tests, skipped=0):
    """A ``jest-junit`` stream declaring ``tests`` cases over one suite.

    The root carries no ``skipped`` attribute, which is jest-junit's own shape and the
    reason :func:`junit` sums that total from the suites.
    """
    cases = []
    for number in range(tests):
        state = "<skipped />" if number < skipped else ""
        cases.append(
            '<testcase classname="src/store/tweetSlice.test.ts" '
            'name="tweetSlice case {0}" time="0.004">{1}</testcase>'.format(number, state))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<testsuites name="jest tests" tests="{0}" failures="0" errors="0" time="1.500">'
        '<testsuite name="src/store/tweetSlice.test.ts" errors="0" failures="0" '
        'skipped="{1}" timestamp="2026-01-01T00:00:00" time="1.500" tests="{0}">{2}'
        "</testsuite></testsuites>".format(tests, skipped, "".join(cases))
    )


def e2e_junit(tests, files=1):
    """A Playwright ``junit`` stream declaring ``tests`` cases over ``files`` suites."""
    suites = []
    for suite in range(files):
        cases = "".join(
            '<testcase name="harness case {0}" classname="spec{1}.spec.ts" '
            'time="0.500"></testcase>'.format(number, suite)
            for number in range(tests // files))
        suites.append(
            '<testsuite name="spec{0}.spec.ts" timestamp="2026-01-01T00:00:00" '
            'hostname="chromium" tests="{1}" failures="0" skipped="0" time="1.000" '
            'errors="0">{2}</testsuite>'.format(suite, tests // files, cases))
    return (
        '<testsuites id="" name="" tests="{0}" failures="0" skipped="0" errors="0" '
        'time="2.000">{1}</testsuites>'.format(tests, "".join(suites))
    )


def jest_summary(registered):
    """The summary of a name-filtered Jest run that registered ``registered`` identities."""
    return (
        "Test Suites: 24 skipped, 0 of 24 total\n"
        "Tests:       {0} skipped, {0} total\n"
        "Snapshots:   0 total\n"
        "Time:        12.14 s\n"
        'Ran all test suites with tests matching "__readiness_probe_that_matches_no_test__".\n'
        .format(registered)
    )


def playwright_listing(discovered, files=1):
    """The tail of a retained ``playwright test --list --reporter=line`` run."""
    listed = "".join(
        "  [chromium] > spec0.spec.ts:{0}:7 > harness case {0}\n".format(number)
        for number in range(discovered))
    return "{0}Total: {1} tests in {2} files\n".format(listed, discovered, files)


def _one_layer_only(tmp_path, monkeypatch, layer, declared, witnessed):
    """Point the extractor at one synthetic stream and its own witness artifact.

    Every other path constant is redirected to a file that does not exist, so the case
    reads only what it wrote and the two streams it is not about stay unavailable.
    """
    absent = list(ISOLATED_CONSTANTS) + ["BACKEND_JUNIT", "BACKEND_COLLECT_ONLY"]
    if layer == "frontend":
        stream = _write(str(tmp_path / "reports" / "jest-junit.xml"), frontend_junit(declared))
        witness = _write(str(tmp_path / "reports" / "load-tests.txt"), jest_summary(witnessed))
        monkeypatch.setattr(extractor, "FRONTEND_JUNIT", stream)
        monkeypatch.setattr(extractor, "FRONTEND_READINESS", witness)
        absent = [name for name in absent
                  if name not in ("FRONTEND_JUNIT", "FRONTEND_READINESS")]
    else:
        stream = _write(str(tmp_path / "reports" / "e2e-junit.xml"), e2e_junit(declared))
        witness = _write(str(tmp_path / "reports" / "list-tests.txt"),
                         playwright_listing(witnessed))
        monkeypatch.setattr(extractor, "E2E_JUNIT", stream)
        monkeypatch.setattr(extractor, "E2E_LIST_TESTS", witness)
        absent = [name for name in absent
                  if name not in ("E2E_JUNIT", "E2E_LIST_TESTS")]
    for constant in absent:
        monkeypatch.setattr(extractor, constant, str(tmp_path / ("absent-" + constant)))
    monkeypatch.setattr(extractor, "REQUIRED", (stream, witness))
    return stream, witness


@pytest.mark.parametrize("layer,label,witness,row_prefix",
                         PARTIAL_LAYERS, ids=PARTIAL_LAYER_IDS)
def test_a_partial_stream_is_withdrawn_rather_than_published(
    tmp_path, monkeypatch, layer, label, witness, row_prefix
):
    """The frontend and e2e streams get the refusal the backend stream already had."""
    stream, _witness = _one_layer_only(
        tmp_path, monkeypatch, layer, declared=6, witnessed=371)

    data = extractor.collect()
    withdrawn = data[layer + "_junit"]

    assert withdrawn["available"] is False
    assert withdrawn["source"] == stream
    assert "declares 6 test cases while {0} 371".format(witness) in withdrawn["reason"]
    assert data[layer + "_partial_stream"] is not None
    # Nothing downstream may carry the partial figure.
    assert data["trend"]["tests"] == 0


@pytest.mark.parametrize("layer,label,witness,row_prefix",
                         PARTIAL_LAYERS, ids=PARTIAL_LAYER_IDS)
def test_a_partial_stream_is_named_on_stderr_and_is_fatal(
    tmp_path, monkeypatch, capsys, layer, label, witness, row_prefix
):
    """A stream that parses, declares cases and is still wrong is reported and fatal."""
    _one_layer_only(tmp_path, monkeypatch, layer, declared=6, witnessed=371)

    status = extractor.main(["--require-all", "--json"])
    reported = capsys.readouterr().err

    assert status == 1
    assert "artifact unusable: {0}".format(label) in reported
    assert "declares 6 test cases while {0} 371".format(witness) in reported


@pytest.mark.parametrize("layer,label,witness,row_prefix",
                         PARTIAL_LAYERS, ids=PARTIAL_LAYER_IDS)
def test_a_complete_stream_is_accepted(
    tmp_path, monkeypatch, capsys, layer, label, witness, row_prefix
):
    """The positive case, so the refusal above cannot pass by always refusing."""
    _one_layer_only(tmp_path, monkeypatch, layer, declared=371, witnessed=371)

    data = extractor.collect()
    extractor.main(["--require-all", "--json"])
    reported = capsys.readouterr().err

    accepted = data[layer + "_junit"]

    assert accepted["available"] is True
    assert accepted["tests"] == 371
    assert data[layer + "_partial_stream"] is None
    assert data["trend"]["tests"] == 371
    assert label not in reported


@pytest.mark.parametrize("layer,label,witness,row_prefix",
                         PARTIAL_LAYERS, ids=PARTIAL_LAYER_IDS)
def test_the_partial_reason_is_stated_in_that_layers_readiness_row(
    tmp_path, monkeypatch, layer, label, witness, row_prefix
):
    """6.4 states what went wrong, rather than falling back to "not produced"."""
    _one_layer_only(tmp_path, monkeypatch, layer, declared=6, witnessed=371)

    rendered = extractor.render(extractor.collect())

    row = [line for line in rendered.split("\n") if line.startswith(row_prefix)]
    assert len(row) == 1
    assert "declares 6 test cases while {0} 371".format(witness) in row[0]
    assert row[0].rstrip().endswith("| FAIL |")


def test_the_extractor_runs_on_the_pinned_interpreter():
    """Standard library only and Python 3.9 compatible, so no manifest changes."""
    assert sys.version_info[:2] >= (3, 9)
    assert extractor.__doc__ is not None

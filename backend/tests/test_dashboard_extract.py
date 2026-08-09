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


def test_the_extractor_runs_on_the_pinned_interpreter():
    """Standard library only and Python 3.9 compatible, so no manifest changes."""
    assert sys.version_info[:2] >= (3, 9)
    assert extractor.__doc__ is not None
